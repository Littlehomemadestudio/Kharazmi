# فلوچارت سیستم Undo/Redo - RASK!

## توضیحات
این فلوچارت سیستم Undo/Redo برنامه RASK! را بر اساس الگوی Command نشان می‌دهد. هر عمل کاربر به یک Command تبدیل شده، در Stack ذخیره می‌شود و قابلیت بازگشت و تکرار دارد.

```mermaid
flowchart TD
    START([شروع سیستم Undo/Redo]) --> INIT[مقداردهی اولیه]
    INIT --> CREATE_UNDO_STACK[ساخت Undo Stack - QUndoStack]
    CREATE_UNDO_STACK --> SET_LIMIT[تنظیم حداکثر اندازه Stack - ۱۰۰]
    SET_LIMIT --> CREATE_REDO_STACK[ساخت Redo Stack]
    CREATE_REDO_STACK --> MACRO_DEPTH[عمق ماکرو = ۰]
    MACRO_DEPTH --> READY[آماده دریافت دستورات]

    READY --> USER_ACTION{عمل کاربر}

    %% ===== COMMAND CREATION =====
    USER_ACTION -->|ایجاد رویداد| CREATE_EVENT_CMD[CreateEventCommand]
    USER_ACTION -->|حذف رویداد| DELETE_EVENT_CMD[DeleteEventCommand]
    USER_ACTION -->|ویرایش رویداد| EDIT_EVENT_CMD[EditEventCommand]
    USER_ACTION -->|ایجاد وظیفه| CREATE_TASK_CMD[CreateTaskCommand]
    USER_ACTION -->|حذف وظیفه| DELETE_TASK_CMD[DeleteTaskCommand]
    USER_ACTION -->|ویرایش وظیفه| EDIT_TASK_CMD[EditTaskCommand]
    USER_ACTION -->|ایجاد وابستگی| CREATE_DEP_CMD[CreateDependencyCommand]
    USER_ACTION -->|حذف وابستگی| DELETE_DEP_CMD[DeleteDependencyCommand]
    USER_ACTION -->|تغییر وضعیت| STATUS_CMD[ChangeStatusCommand]
    USER_ACTION -->|Drag & Drop| MOVE_CMD[MoveTaskCommand]
    USER_ACTION -->|Ctrl+Z| UNDO_REQ[درخواست Undo]
    USER_ACTION -->|Ctrl+Y| REDO_REQ[درخواست Redo]
    USER_ACTION -->|Ctrl+Shift+Z| REDO_REQ

    CREATE_EVENT_CMD --> CMD_EXECUTE
    DELETE_EVENT_CMD --> CMD_EXECUTE
    EDIT_EVENT_CMD --> CMD_EXECUTE
    CREATE_TASK_CMD --> CMD_EXECUTE
    DELETE_TASK_CMD --> CMD_EXECUTE
    EDIT_TASK_CMD --> CMD_EXECUTE
    CREATE_DEP_CMD --> CMD_EXECUTE
    DELETE_DEP_CMD --> CMD_EXECUTE
    STATUS_CMD --> CMD_EXECUTE
    MOVE_CMD --> CMD_EXECUTE

    %% ===== COMMAND EXECUTION =====
    CMD_EXECUTE[اجرای Command] --> SAVE_STATE[ذخیره State قبلی - Memento]
    SAVE_STATE --> DO_ACTION[اجرای عمل واقعی]
    DO_ACTION --> SUCCESS{عمل موفق؟}

    SUCCESS -->|خیر| ROLLBACK[بازگشت به State قبلی]
    ROLLBACK --> NOTIFY_ERR[اعلان خطا به کاربر]
    NOTIFY_ERR --> READY

    SUCCESS -->|بله| MACRO_CHECK{در حال ضبط ماکرو؟}

    MACRO_CHECK -->|بله| ADD_TO_MACRO[افزودن به ماکرو جاری]
    MACRO_CHECK -->|خیر| PUSH_UNDO

    ADD_TO_MACRO --> UPDATE_UI[به‌روزرسانی رابط کاربری]
    UPDATE_UI --> READY

    %% ===== PUSH TO UNDO STACK =====
    PUSH_UNDO[فشردن در Undo Stack] --> CLEAR_REDO[پاک کردن Redo Stack]
    CLEAR_REDO --> STACK_FULL{Stack پر است؟}

    STACK_FULL -->|بله| POP_OLDEST[حذف قدیمی‌ترین Command]
    STACK_FULL -->|خیر| PUSH_CMD

    POP_OLDEST --> PUSH_CMD[فشردن Command جدید]
    PUSH_CMD --> UPDATE_UI

    %% ===== UNDO FLOW =====
    UNDO_REQ[درخواست Undo] --> UNDO_STACK_EMPTY{Undo Stack خالی؟}

    UNDO_STACK_EMPTY -->|بله| NO_UNDO[عدم امکان Undo - صدای هشدار]
    UNDO_STACK_EMPTY -->|خیر| POP_UNDO[خارج کردن Command از Undo Stack]

    POP_UNDO --> CMD_UNDO[فراخوانی command.undo]
    CMD_UNDO --> RESTORE_STATE[بازیابی State قبلی از Memento]
    RESTORE_STATE --> UPDATE_DB[به‌روزرسانی پایگاه داده]

    UPDATE_DB --> PUSH_REDO[فشردن در Redo Stack]
    PUSH_REDO --> UPDATE_UI_UNDO[به‌روزرسانی UI]
    UPDATE_UI_UNDO --> READY

    %% ===== REDO FLOW =====
    REDO_REQ[درخواست Redo] --> REDO_STACK_EMPTY{Redo Stack خالی؟}

    REDO_STACK_EMPTY -->|بله| NO_REDO[عدم امکان Redo - صدای هشدار]
    REDO_STACK_EMPTY -->|خیر| POP_REDO[خارج کردن Command از Redo Stack]

    POP_REDO --> CMD_REDO[فراخوانی command.redo]
    CMD_REDO --> REAPPLY_STATE[اعمال مجدد State]
    REAPPLY_STATE --> UPDATE_DB_REDO[به‌روزرسانی پایگاه داده]

    UPDATE_DB_REDO --> PUSH_UNDO_REDO[فشردن در Undo Stack]
    PUSH_UNDO_REDO --> UPDATE_UI_REDO[به‌روزرسانی UI]
    UPDATE_UI_REDO --> READY

    %% ===== MACRO COMMAND =====
    MACRO_START[شروع ماکرو - beginMacro] --> INCR_DEPTH[افزایش عمق ماکرو]
    INCR_DEPTH --> READY

    MACRO_END[پایان ماکرو - endMacro] --> DECR_DEPTH[کاهش عمق ماکرو]
    DECR_DEPTH --> MERGE_CMDS[ادغام تمام Commandهای ماکرو]
    MERGE_CMDS --> PUSH_MACRO[فشردن ماکرو به عنوان یک Command]
    PUSH_MACRO --> UPDATE_UI

    %% ===== COMMAND MERGE =====
    MERGE_CHECK{Command قابل ادغام؟} -->|بله| MERGE_PREV[ادغام با Command قبلی]
    MERGE_CHECK -->|خیر| PUSH_UNDO

    MERGE_PREV --> UPDATE_MERGED[به‌روزرسانی Command ادغام‌شده]
    UPDATE_MERGED --> UPDATE_UI

    %% ===== UI STATE =====
    UPDATE_UI --> BTN_STATE[به‌روزرسانی وضعیت دکمه‌ها]
    BTN_STATE --> UNDO_BTN{Undo Stack خالی؟}
    UNDO_BTN -->|بله| DISABLE_UNDO[غیرفعال کردن دکمه Undo]
    UNDO_BTN -->|خیر| ENABLE_UNDO[فعال کردن دکمه Undo + متن]

    DISABLE_UNDO --> REDO_BTN
    ENABLE_UNDO --> REDO_BTN

    REDO_BTN{Redo Stack خالی؟}
    REDO_BTN -->|بله| DISABLE_REDO[غیرفعال کردن دکمه Redo]
    REDO_BTN -->|خیر| ENABLE_REDO[فعال کردن دکمه Redo + متن]

    DISABLE_REDO --> READY
    ENABLE_REDO --> READY

    style START fill:#4CAF50,color:#fff
    style READY fill:#2196F3,color:#fff
    style CMD_EXECUTE fill:#FF9800,color:#fff
    style PUSH_UNDO fill:#9C27B0,color:#fff
    style CMD_UNDO fill:#E91E63,color:#fff
    style CMD_REDO fill:#00BCD4,color:#fff
    style SUCCESS fill:#FFC107,color:#000
    style MACRO_CHECK fill:#FFC107,color:#000
    style STACK_FULL fill:#FFC107,color:#000
    style UNDO_STACK_EMPTY fill:#FFC107,color:#000
    style REDO_STACK_EMPTY fill:#FFC107,color:#000
    style MERGE_CHECK fill:#FFC107,color:#000
    style UNDO_BTN fill:#FFC107,color:#000
    style REDO_BTN fill:#FFC107,color:#000
    style USER_ACTION fill:#FFC107,color:#000
```

## ساختار Command الگو

```python
class BaseCommand(QUndoCommand):
    def __init__(self, description):
        super().__init__(description)
        self.memento = None  # State قبلی

    def redo(self):
        """اجرای عمل - اولین بار و هنگام Redo"""
        pass

    def undo(self):
        """بازگشت عمل - هنگام Undo"""
        pass

    def save_state(self):
        """ذخیره State فعلی قبل از تغییر"""
        pass

    def restore_state(self):
        """بازیابی State ذخیره‌شده"""
        pass
```

## انواع Command ها

| Command | عمل redo | عمل undo |
|---|---|---|
| **CreateEventCommand** | ایجاد رویداد | حذف رویداد |
| **DeleteEventCommand** | حذف رویداد | بازیابی رویداد |
| **EditEventCommand** | اعمال تغییرات | بازگشت تغییرات |
| **CreateTaskCommand** | ایجاد وظیفه | حذف وظیفه |
| **DeleteTaskCommand** | حذف وظیفه | بازیابی وظیفه |
| **CreateDependencyCommand** | ایجاد وابستگی | حذف وابستگی |
| **ChangeStatusCommand** | تغییر وضعیت | بازگشت وضعیت |
| **MoveTaskCommand** | جابجایی وظیفه | بازگشت به مکان قبلی |

## توضیح اجزای اصلی

1. **الگوی Command**: هر عمل کاربر به یک شیء Command تبدیل می‌شود.
2. **الگوی Memento**: State قبل از هر عمل ذخیره می‌شود تا قابل بازگشت باشد.
3. **Macro Command**: چند عمل می‌توانند در یک ماکرو ادغام شوند و به‌صورت یک Undo برگردند.
4. **Command Merge**: عملیات مشابه متوالی (مثل تایپ مداوم) ادغام می‌شوند.
5. **پاکسازی Redo Stack**: هر عمل جدید، Redo Stack را پاک می‌کند.
