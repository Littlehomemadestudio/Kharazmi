"""تست‌های جامع الگوریتم‌ها — مرتب‌سازی توپولوژیک، تشخیص چرخه، مسیر بحرانی، پرت، مونت‌کارلو، هموارسازی منابع"""

import math
from datetime import datetime

import pytest

from kharazmi.algorithms.topological_sort import topological_sort, CycleError
from kharazmi.algorithms.cycle_detection import has_cycle, find_any_cycle
from kharazmi.algorithms.critical_path import run_cpm, CPMResult
from kharazmi.algorithms.pert import run_pert, PERTSummary, ensure_pert_estimates
from kharazmi.algorithms.monte_carlo import run_monte_carlo, MonteCarloResult
from kharazmi.algorithms.resource_leveling import run_resource_leveling, LevelingResult
from kharazmi.core.task import Task
from kharazmi.core.project import Project
from kharazmi.core.dependency import Dependency
from kharazmi.core.value_objects import (
    TaskId, Duration, PertEstimate, Resource, ResourceAllocation, Slack,
)
from kharazmi.core.enums import DependencyType, Priority


# ═══════════════════════════════════════════════════════════════════
#  مرتب‌سازی توپولوژیک
# ═══════════════════════════════════════════════════════════════════


class TestTopologicalSort:
    """تست‌های مرتب‌سازی توپولوژیک — الگوریتم کان"""

    # زنجیره خطی — ترتیب صحیح وابستگی‌ها
    def test_linear_chain_sorts_correctly(self, project_with_tasks):
        """زنجیره خطی: A→B→C→D باید دقیقاً به همین ترتیب برگردد"""
        order = topological_sort(project_with_tasks)
        # یافتن نام وظایف بر اساس ترتیب
        task_names = []
        for tid in order:
            task = project_with_tasks.get_task(tid)
            task_names.append(task.title)

        # ترتیب باید: طراحی، پیاده‌سازی، تست، استقرار
        assert task_names == ["طراحی", "پیاده‌سازی", "تست", "استقرار"]

    # وظایف موازی — هر دو ترتیب معتبر ممکن است
    def test_parallel_tasks_both_valid_orders(self, project):
        """وظایف موازی بدون وابستگی بینشان — هر دو ترتیب معتبر است"""
        t1 = project.create_task("آلفا", duration=Duration(480))
        t2 = project.create_task("بتا", duration=Duration(480))
        # بدون وابستگی — هر ترتیبی معتبر است
        order = topological_sort(project)
        assert len(order) == 2
        # هر دو وظیفه باید در خروجی باشند
        order_values = {t.value for t in order}
        assert t1.id.value in order_values
        assert t2.id.value in order_values

    # پروژه خالی — نتیجه خالی
    def test_empty_project_returns_empty(self, project):
        """پروژه بدون وظیفه باید لیست خالی برگرداند"""
        order = topological_sort(project)
        assert order == []

    # تشخیص چرخه — باید CycleError بدهد
    def test_cycle_raises_cycle_error(self, project):
        """گراف چرخه‌دار باید CycleError تولید کند"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(60))
        t2 = project.create_task("وظیفه ۲", duration=Duration(60))
        t3 = project.create_task("وظیفه ۳", duration=Duration(60))
        # ساخت چرخه: ۱→۲→۳→۱
        # از آنجایی که پروژه جلوی افزودن وابستگی چرخه‌ای را می‌گیرد،
        # باید مستقیماً وابستگی‌ها را به دیکشنری داخلی اضافه کنیم
        project._deps[(t1.id.value, t2.id.value, "FS")] = Dependency(
            t1.id, t2.id, DependencyType.FINISH_START
        )
        project._deps[(t2.id.value, t3.id.value, "FS")] = Dependency(
            t2.id, t3.id, DependencyType.FINISH_START
        )
        project._deps[(t3.id.value, t1.id.value, "FS")] = Dependency(
            t3.id, t1.id, DependencyType.FINISH_START
        )
        with pytest.raises(CycleError):
            topological_sort(project)

    # گراف الماسی — وابستگی الماسی
    def test_diamond_dependency_graph(self, project):
        """گراف الماسی: A→B, A→C, B→D, C→D — A قبل از B و C، D بعد از هر دو"""
        t_a = project.create_task("A", duration=Duration(60))
        t_b = project.create_task("B", duration=Duration(60))
        t_c = project.create_task("C", duration=Duration(60))
        t_d = project.create_task("D", duration=Duration(60))
        project.add_dependency(Dependency(t_a.id, t_b.id, DependencyType.FINISH_START))
        project.add_dependency(Dependency(t_a.id, t_c.id, DependencyType.FINISH_START))
        project.add_dependency(Dependency(t_b.id, t_d.id, DependencyType.FINISH_START))
        project.add_dependency(Dependency(t_c.id, t_d.id, DependencyType.FINISH_START))

        order = topological_sort(project)
        order_values = [t.value for t in order]

        # A باید قبل از B و C بیاید
        assert order_values.index(t_a.id.value) < order_values.index(t_b.id.value)
        assert order_values.index(t_a.id.value) < order_values.index(t_c.id.value)
        # D باید بعد از B و C بیاید
        assert order_values.index(t_d.id.value) > order_values.index(t_b.id.value)
        assert order_values.index(t_d.id.value) > order_values.index(t_c.id.value)

    # تک وظیفه — بدون وابستگی
    def test_single_task(self, project):
        """پروژه با یک وظیفه — باید فقط همان وظیفه برگردد"""
        t = project.create_task("تنها", duration=Duration(60))
        order = topological_sort(project)
        assert len(order) == 1
        assert order[0] == t.id


# ═══════════════════════════════════════════════════════════════════
#  تشخیص چرخه
# ═══════════════════════════════════════════════════════════════════


class TestCycleDetection:
    """تست‌های تشخیص چرخه — جستجوی عمق‌اول"""

    # بدون چرخه — باید False برگرداند
    def test_no_cycle_returns_false(self, project_with_tasks):
        """گراف بدون چرخه (DAG) — has_cycle باید False برگرداند"""
        assert has_cycle(project_with_tasks) is False

    # چرخه ساده — باید True برگرداند
    def test_simple_cycle_returns_true(self, project):
        """گراف با چرخه ساده — has_cycle باید True برگرداند"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(60))
        t2 = project.create_task("وظیفه ۲", duration=Duration(60))
        t3 = project.create_task("وظیفه ۳", duration=Duration(60))
        # تزریق مستقیم وابستگی‌های چرخه‌ای
        project._deps[(t1.id.value, t2.id.value, "FS")] = Dependency(
            t1.id, t2.id, DependencyType.FINISH_START
        )
        project._deps[(t2.id.value, t3.id.value, "FS")] = Dependency(
            t2.id, t3.id, DependencyType.FINISH_START
        )
        project._deps[(t3.id.value, t1.id.value, "FS")] = Dependency(
            t3.id, t1.id, DependencyType.FINISH_START
        )
        assert has_cycle(project) is True

    # یافتن مسیر چرخه — find_any_cycle
    def test_find_any_cycle_returns_cycle_path(self, project):
        """find_any_cycle باید مسیر چرخه را برگرداند"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(60))
        t2 = project.create_task("وظیفه ۲", duration=Duration(60))
        t3 = project.create_task("وظیفه ۳", duration=Duration(60))
        project._deps[(t1.id.value, t2.id.value, "FS")] = Dependency(
            t1.id, t2.id, DependencyType.FINISH_START
        )
        project._deps[(t2.id.value, t3.id.value, "FS")] = Dependency(
            t2.id, t3.id, DependencyType.FINISH_START
        )
        project._deps[(t3.id.value, t1.id.value, "FS")] = Dependency(
            t3.id, t1.id, DependencyType.FINISH_START
        )
        cycle = find_any_cycle(project)
        assert cycle is not None
        # مسیر چرخه باید حداقل ۲ گره داشته باشد (شروع و پایان یکی هستند)
        assert len(cycle) >= 2
        # اول و آخر باید یکی باشند (چرخه بسته)
        assert cycle[0] == cycle[-1]

    # خودحلقه — چرخه دوگره‌ای
    def test_self_loop_detection(self, project):
        """چرخه دوگره‌ای: A→B و B→A — باید چرخه تشخیص داده شود"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(60))
        t2 = project.create_task("وظیفه ۲", duration=Duration(60))
        # چرخه دوگره‌ای: t1→t2 و t2→t1
        project._deps[(t1.id.value, t2.id.value, "FS")] = Dependency(
            t1.id, t2.id, DependencyType.FINISH_START
        )
        project._deps[(t2.id.value, t1.id.value, "FS")] = Dependency(
            t2.id, t1.id, DependencyType.FINISH_START
        )
        assert has_cycle(project) is True
        cycle = find_any_cycle(project)
        assert cycle is not None

    # بدون چرخه در DAG
    def test_no_cycle_in_dag(self, project_with_parallel):
        """پروژه موازی بدون چرخه — has_cycle باید False برگرداند"""
        assert has_cycle(project_with_parallel) is False

    # DAG بدون وابستگی — بدون چرخه
    def test_no_cycle_in_isolated_tasks(self, project):
        """وظایف بدون وابستگی — بدون چرخه"""
        project.create_task("وظیفه ۱", duration=Duration(60))
        project.create_task("وظیفه ۲", duration=Duration(60))
        project.create_task("وظیفه ۳", duration=Duration(60))
        assert has_cycle(project) is False
        assert find_any_cycle(project) is None

    # پروژه خالی
    def test_empty_project_no_cycle(self, project):
        """پروژه خالی — بدون چرخه"""
        assert has_cycle(project) is False
        assert find_any_cycle(project) is None


# ═══════════════════════════════════════════════════════════════════
#  مسیر بحرانی
# ═══════════════════════════════════════════════════════════════════


class TestCriticalPath:
    """تست‌های الگوریتم مسیر بحرانی — CPM"""

    # زنجیره ساده — همه وظایف بحرانی
    def test_simple_chain_all_critical(self, project_with_tasks):
        """در زنجیره خطی همه وظایف روی مسیر بحرانی هستند"""
        start = datetime(2025, 1, 6, 9, 0)  # دوشنبه
        result = run_cpm(project_with_tasks, start_anchor=start)
        assert result.ok is True
        # ۴ وظیفه در زنجیره — همه باید بحرانی باشند
        assert len(result.critical_path) == 4
        for task in project_with_tasks.tasks():
            assert task.slack is not None
            assert task.slack.is_critical is True

    # مسیرهای موازی — مسیر طولانی‌تر بحرانی
    def test_parallel_paths_longer_is_critical(self, project_with_parallel):
        """مسیر بحرانی باید مسیر طولانی‌تر (الف) باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_parallel, start_anchor=start)
        assert result.ok is True
        # مسیر بحرانی: شروع + مسیر الف + پایان
        critical_ids = {tid.value for tid in result.critical_path}
        # یافتن وظیفه «مسیر الف» (مدت ۱۴۴۰ دقیقه)
        for task in project_with_parallel.tasks():
            if task.title == "مسیر الف":
                assert task.id.value in critical_ids
                assert task.is_critical is True
            elif task.title == "مسیر ب":
                # مسیر ب کوتاه‌تر است — نباید بحرانی باشد
                assert task.is_critical is False
                assert task.slack is not None
                assert task.slack.total_slack.minutes > 0

    # ویژگی ok در CPMResult
    def test_cpm_result_ok_property(self, project_with_tasks):
        """CPMResult.ok باید True باشد وقتی چرخه‌ای وجود ندارد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_tasks, start_anchor=start)
        assert result.ok is True

    # CPMResult.ok باید False باشد وقتی چرخه وجود دارد
    def test_cpm_result_ok_false_on_cycle(self, project):
        """CPMResult.ok باید False باشد وقتی گراف چرخه‌ای باشد"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(60))
        t2 = project.create_task("وظیفه ۲", duration=Duration(60))
        project._deps[(t1.id.value, t2.id.value, "FS")] = Dependency(
            t1.id, t2.id, DependencyType.FINISH_START
        )
        project._deps[(t2.id.value, t1.id.value, "FS")] = Dependency(
            t2.id, t1.id, DependencyType.FINISH_START
        )
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project, start_anchor=start)
        assert result.ok is False
        assert result.cycle_error is not None

    # مسیر بحرانی شامل وظایف صحیح
    def test_critical_path_contains_correct_tasks(self, project_with_parallel):
        """مسیر بحرانی باید شامل وظایف مسیر طولانی‌تر باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_parallel, start_anchor=start)
        # شروع و پایان باید در مسیر بحرانی باشند
        critical_names = set()
        for tid in result.critical_path:
            task = project_with_parallel.get_task(tid)
            critical_names.add(task.title)
        assert "شروع" in critical_names
        assert "پایان" in critical_names
        assert "مسیر الف" in critical_names
        assert "مسیر ب" not in critical_names

    # محاسبه مدت پروژه
    def test_project_duration_calculation(self, project_with_tasks):
        """مدت پروژه باید برابر مجموع مدت تمام وظایف زنجیره‌ای باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_tasks, start_anchor=start)
        # مجموع کار: ۴۸۰ + ۹۶۰ + ۴۸۰ + ۲۴۰ = ۲۱۶۰ دقیقه
        # CPM مدت را بر اساس زمان تقویمی محاسبه می‌کند:
        # از دوشنبه ۹:۰۰ تا جمعه ۱۳:۰۰ = ۴ روز × ۲۴ ساعت + ۴ ساعت = ۱۰۰ ساعت = ۶۰۰۰ دقیقه
        assert result.project_duration.minutes == 6000
        # همچنین بررسی می‌کنیم که مدت کاری مجموع برابر ۲۱۶۰ باشد
        total_work = sum(t.effective_duration.minutes for t in project_with_tasks.tasks())
        assert total_work == 2160

    # محاسبه شل — وظایف غیربحرانی شل مثبت دارند
    def test_slack_non_critical_tasks_have_positive_slack(self, project_with_parallel):
        """وظایف غیربحرانی باید شل مثبت (total_slack > 0) داشته باشند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_parallel, start_anchor=start)
        for task in project_with_parallel.tasks():
            if task.title == "مسیر ب":
                assert task.slack is not None
                assert task.slack.total_slack.minutes > 0
                # شل آزاد هم باید مثبت باشد
                assert task.slack.free_slack.minutes >= 0

    # پروژه خالی
    def test_empty_project_cpm(self, project):
        """پروژه خالی — CPM باید نتیجه معتبر با مسیر بحرانی خالی برگرداند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project, start_anchor=start)
        assert result.ok is True
        assert result.critical_path == []
        assert result.project_duration.minutes == 0

    # شل بحرانی صفر
    def test_critical_tasks_have_zero_slack(self, project_with_tasks):
        """وظایف بحرانی باید شل صفر داشته باشند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_tasks, start_anchor=start)
        for task in project_with_tasks.tasks():
            assert task.slack is not None
            if task.is_critical:
                assert task.slack.total_slack.minutes == 0

    # early_start و early_finish برای همه وظایف
    def test_early_start_and_finish_set(self, project_with_tasks):
        """پس از CPM، تمام وظایف باید early_start و early_finish داشته باشند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_tasks, start_anchor=start)
        for task in project_with_tasks.tasks():
            assert task.early_start is not None
            assert task.early_finish is not None

    # late_start و late_finish برای همه وظایف
    def test_late_start_and_finish_set(self, project_with_tasks):
        """پس از CPM، تمام وظایف باید late_start و late_finish داشته باشند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_cpm(project_with_tasks, start_anchor=start)
        for task in project_with_tasks.tasks():
            assert task.late_start is not None
            assert task.late_finish is not None


# ═══════════════════════════════════════════════════════════════════
#  پرت (PERT)
# ═══════════════════════════════════════════════════════════════════


class TestPERT:
    """تست‌های تحلیل PERT — برآورد زمان و احتمال"""

    # فرمول مدت مورد انتظار PERT: (O+4M+P)/6
    def test_pert_expected_duration_formula(self):
        """فرمول مدت مورد انتظار: (O+4M+P)/6"""
        pert = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(180),
        )
        # (60 + 4*120 + 180) / 6 = (60 + 480 + 180) / 6 = 720 / 6 = 120
        assert pert.expected.minutes == 120

    # انحراف معیار PERT: (P-O)/6
    def test_pert_std_dev_formula(self):
        """انحراف معیار: (P-O)/6"""
        pert = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(180),
        )
        # (180 - 60) / 6 = 120 / 6 = 20
        assert pert.std_dev == 20.0

    # واریانس PERT
    def test_pert_variance_calculation(self):
        """واریانس: ((P-O)/6)²"""
        pert = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(180),
        )
        # (20)² = 400
        assert pert.variance == 400.0

    # اجرای PERT با پروژه
    def test_run_pert_with_project(self, project_with_tasks):
        """اجرای run_pert روی پروژه باید PERTSummary معتبر برگرداند"""
        start = datetime(2025, 1, 6, 9, 0)
        # ابتدا PERT estimates تنظیم کنیم
        for task in project_with_tasks.tasks():
            base = task.duration.minutes
            task.pert = PertEstimate(
                optimistic=Duration(max(1, int(base * 0.8))),
                most_likely=Duration(base),
                pessimistic=Duration(int(base * 1.2)),
            )
        result = run_pert(project_with_tasks, start_anchor=start)
        assert isinstance(result, PERTSummary)
        assert result.expected_duration.minutes > 0
        assert result.variance >= 0
        assert result.std_dev >= 0
        assert len(result.critical_path) > 0

    # محاسبه احتمال با هدف مشخص
    def test_probability_by_target(self):
        """محاسبه احتمال اتمام پروژه تا هدف مشخص"""
        pert = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(180),
        )
        # ساختن PERTSummary دستی
        summary = PERTSummary(
            expected_duration=pert.expected,
            variance=pert.variance,
            std_dev=pert.std_dev,
            critical_path=[],
        )
        # هدف = مدت مورد انتظار — احتمال باید حدود ۵۰٪ باشد
        prob = summary.probability_by(pert.expected.minutes)
        assert 0.45 <= prob <= 0.55  # حدود ۰.۵

        # هدف بسیار بزرگ — احتمال نزدیک ۱
        prob_high = summary.probability_by(pert.expected.minutes + 1000)
        assert prob_high > 0.99

        # هدف بسیار کوچک — احتمال نزدیک ۰
        prob_low = summary.probability_by(0)
        assert prob_low < 0.01

    # PERT با برآورد یکسان (بدون عدم قطعیت)
    def test_pert_deterministic_no_variance(self):
        """وقتی O=M=P، واریانس و انحراف معیار باید صفر باشند"""
        pert = PertEstimate(
            optimistic=Duration(120),
            most_likely=Duration(120),
            pessimistic=Duration(120),
        )
        assert pert.variance == 0.0
        assert pert.std_dev == 0.0
        assert pert.expected.minutes == 120

    # ensure_pert_estimates — ساخت خودکار برآورد
    def test_ensure_pert_estimates_synthesizes(self, project_with_tasks):
        """ensure_pert_estimates باید برای وظایف بدون PERT، برآورد بسازد"""
        for task in project_with_tasks.tasks():
            assert task.pert is None
        ensure_pert_estimates(project_with_tasks)
        for task in project_with_tasks.tasks():
            assert task.pert is not None
            # برآورد ساده شده: ۸۰٪ تا ۱۲۰٪ مدت اصلی
            base = task.duration.minutes
            assert task.pert.optimistic.minutes == max(1, int(base * 0.8))
            assert task.pert.most_likely.minutes == base
            assert task.pert.pessimistic.minutes == int(base * 1.2)

    # run_pert روی پروژه خالی
    def test_run_pert_empty_project(self, project):
        """پروژه خالی — PERT باید واریانس صفر برگرداند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_pert(project, start_anchor=start)
        assert result.variance == 0.0
        assert result.std_dev == 0.0
        assert result.critical_path == []

    # اعتبارسنجی ترتیب PERT: O ≤ M ≤ P
    def test_pert_validation_order(self):
        """برآورد PERT نامعتبر (O > M) باید ValueError بدهد"""
        with pytest.raises(ValueError):
            PertEstimate(
                optimistic=Duration(200),
                most_likely=Duration(100),
                pessimistic=Duration(300),
            )


# ═══════════════════════════════════════════════════════════════════
#  مونت‌کارلو
# ═══════════════════════════════════════════════════════════════════


class TestMonteCarlo:
    """تست‌های شبیه‌سازی مونت‌کارلو — برآورد ریسک"""

    # اجرا با seed برای تکرارپذیری
    def test_run_with_seed_reproducible(self, project_with_tasks):
        """اجرای مونت‌کارلو با seed باید نتایج تکرارپذیر بدهد"""
        start = datetime(2025, 1, 6, 9, 0)
        # اجرای اول
        result1 = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42, start_anchor=start
        )
        # اجرای دوم با همان seed
        result2 = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42, start_anchor=start
        )
        assert result1.mean_minutes == result2.mean_minutes
        assert result1.p10_minutes == result2.p10_minutes
        assert result1.p90_minutes == result2.p90_minutes

    # نتایج آماری صحیح
    def test_result_has_correct_statistics(self, project_with_tasks):
        """نتیجه باید شامل تمام آمارهای مورد انتظار باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42, start_anchor=start
        )
        assert isinstance(result, MonteCarloResult)
        assert result.iterations > 0
        assert result.mean_minutes > 0
        assert result.median_minutes > 0
        assert result.p10_minutes > 0
        assert result.p50_minutes > 0
        assert result.p90_minutes > 0
        assert result.p95_minutes > 0
        # ترتیب منطقی صدک‌ها
        assert result.p10_minutes <= result.p50_minutes
        assert result.p50_minutes <= result.p90_minutes
        assert result.p90_minutes <= result.p95_minutes

    # تعداد تکرارها
    def test_iterations_count_matches(self, project_with_tasks):
        """تعداد تکرارها باید با مقدار درخواستی مطابقت کند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_monte_carlo(
            project_with_tasks, iterations=50, seed=42, start_anchor=start
        )
        assert result.iterations == 50

    # با PERT قطعی (O=M=P)، نتیجه باید نزدیک CPM باشد
    def test_deterministic_pert_close_to_cpm(self, project):
        """وقتی O=M=P، همه نمونه‌ها یکسان هستند و نتیجه باید دقیقاً CPM باشد"""
        t1 = project.create_task("وظیفه ۱", duration=Duration(480))
        t2 = project.create_task("وظیفه ۲", duration=Duration(480))
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
        # تنظیم PERT قطعی
        for task in project.tasks():
            task.pert = PertEstimate(
                optimistic=Duration(480),
                most_likely=Duration(480),
                pessimistic=Duration(480),
            )
        start = datetime(2025, 1, 6, 9, 0)
        # ابتدا CPM را با مقادیر قطعی اجرا می‌کنیم
        cpm_result = run_cpm(project, start_anchor=start)
        cpm_duration = cpm_result.project_duration.minutes
        # اجرای مونت‌کارلو
        result = run_monte_carlo(
            project, iterations=50, seed=42, start_anchor=start
        )
        # با PERT قطعی، همه تکرارها باید یکسان باشند
        assert result.mean_minutes == cpm_duration
        assert result.min_minutes == result.max_minutes

    # هیستوگرام غیرخالی
    def test_histogram_non_empty(self, project_with_tasks):
        """هیستوگرام باید غیرخالی باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42, start_anchor=start
        )
        assert len(result.histogram) > 0
        assert sum(result.histogram) > 0

    # تبدیل به دیکشنری
    def test_to_dict(self, project_with_tasks):
        """MonteCarloResult.to_dict باید دیکشنری معتبر برگرداند"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_monte_carlo(
            project_with_tasks, iterations=50, seed=42, start_anchor=start
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "iterations" in d
        assert "mean_minutes" in d
        assert "p10_minutes" in d
        assert "p90_minutes" in d
        assert "histogram" in d

    # احتمال اتمام تا هدف
    def test_probability_within_target(self, project_with_tasks):
        """احتمال اتمام پروژه تا هدف مشخص باید بین ۰ و ۱ باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        # هدف بزرگ — احتمال باید بالا باشد
        result = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42,
            target_minutes=10000, start_anchor=start,
        )
        assert 0.0 <= result.probability_within_target <= 1.0
        assert result.probability_within_target > 0.9  # هدف بسیار بزرگ

    # min و max
    def test_min_max_minutes(self, project_with_tasks):
        """min_minutes باید کمتر از max_minutes باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_monte_carlo(
            project_with_tasks, iterations=100, seed=42, start_anchor=start
        )
        assert result.min_minutes <= result.max_minutes
        assert result.min_minutes > 0


# ═══════════════════════════════════════════════════════════════════
#  هموارسازی منابع
# ═══════════════════════════════════════════════════════════════════


class TestResourceLeveling:
    """تست‌های هموارسازی منابع — بهینه‌سازی تخصیص منابع"""

    # بدون تداخل — چیزی برای حل نیست
    def test_no_conflicts_nothing_to_resolve(self, project_with_tasks):
        """بدون تداخل منابع — هیچ وظیفه‌ای نباید جابجا شود"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project_with_tasks, start_anchor=start)
        assert isinstance(result, LevelingResult)
        assert result.conflicts_resolved == 0
        assert result.shifted_tasks == []

    # تداخل منابع — وظایف جابجا می‌شوند
    def test_resource_conflict_tasks_get_shifted(self, project):
        """تداخل منابع — وظایف باید جابجا شوند"""
        # ساخت منبع با ظرفیت محدود
        developer = Resource(name="توسعه‌دهنده", capacity_per_day=1.0)
        # دو وظیفه موازی با منبع مشترک
        t1 = project.create_task("وظیفه ۱", duration=Duration(480))
        t1.assign_resource(ResourceAllocation(developer, 1.0))
        t2 = project.create_task("وظیفه ۲", duration=Duration(480))
        t2.assign_resource(ResourceAllocation(developer, 1.0))
        # بدون وابستگی — هر دو از همان نقطه شروع می‌شوند
        # تداخل منابع: ۲ وظیفه × ۱.۰ بار = ۲.۰ > ظرفیت ۱.۰
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project, start_anchor=start)
        assert isinstance(result, LevelingResult)
        # باید حداقل یک وظیفه جابجا شده باشد یا تداخل باقی‌مانده باشد
        assert result.conflicts_resolved > 0 or result.conflicts_remaining > 0

    # LevelingResult فیلدهای صحیح
    def test_leveling_result_has_correct_fields(self, project_with_tasks):
        """LevelingResult باید شامل تمام فیلدهای مورد انتظار باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project_with_tasks, start_anchor=start)
        assert hasattr(result, "conflicts_resolved")
        assert hasattr(result, "conflicts_remaining")
        assert hasattr(result, "shifted_tasks")
        assert hasattr(result, "cpm")
        assert isinstance(result.cpm, CPMResult)

    # پروژه بدون منابع
    def test_no_resources_no_leveling(self, project_with_tasks):
        """پروژه بدون تخصیص منابع — هیچ هموارسازی لازم نیست"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project_with_tasks, start_anchor=start)
        assert result.conflicts_resolved == 0
        assert result.conflicts_remaining == 0
        assert result.shifted_tasks == []

    # پروژه خالی
    def test_empty_project_leveling(self, project):
        """پروژه خالی — هموارسازی بدون تغییر"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project, start_anchor=start)
        assert result.conflicts_resolved == 0
        assert result.conflicts_remaining == 0
        assert result.shifted_tasks == []

    # CPM در LevelingResult باید معتبر باشد
    def test_leveling_cpm_is_valid(self, project_with_tasks):
        """CPM داخل LevelingResult باید معتبر باشد"""
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project_with_tasks, start_anchor=start)
        assert result.cpm.ok is True

    # تداخل با سه وظیفه موازی
    def test_three_parallel_tasks_with_resource_conflict(self, project):
        """سه وظیفه موازی با منبع مشترک — تداخل شدیدتر"""
        developer = Resource(name="توسعه‌دهنده", capacity_per_day=1.0)
        t1 = project.create_task("وظیفه ۱", duration=Duration(480))
        t1.assign_resource(ResourceAllocation(developer, 1.0))
        t2 = project.create_task("وظیفه ۲", duration=Duration(480))
        t2.assign_resource(ResourceAllocation(developer, 1.0))
        t3 = project.create_task("وظیفه ۳", duration=Duration(480))
        t3.assign_resource(ResourceAllocation(developer, 1.0))
        start = datetime(2025, 1, 6, 9, 0)
        result = run_resource_leveling(project, start_anchor=start)
        # سه وظیفه موازی با ظرفیت ۱ — باید تداخل شدید باشد
        assert result.conflicts_resolved > 0 or result.conflicts_remaining > 0
