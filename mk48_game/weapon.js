class Weapon {
    constructor(type, owner) {
        this.type = type;
        this.owner = owner;
        this.x = 0;
        this.y = 0;
        this.vx = 0;
        this.vy = 0;
        this.angle = 0;
        this.damage = 0;
        this.speed = 0;
        this.lifetime = 0;
        this.maxLifetime = 0;
        this.size = 0;
        this.active = true;
        this.trail = [];
    }

    update(deltaTime) {
        this.x += this.vx * deltaTime;
        this.y += this.vy * deltaTime;
        this.lifetime += deltaTime;

        if (this.type === 'torpedo') {
            this.createTrail();
        }

        if (this.lifetime >= this.maxLifetime) {
            this.active = false;
        }
    }

    createTrail() {
        if (Math.random() < 0.3) {
            particleSystem.createTorpedoTrail(this.x, this.y);
        }
    }

    render(ctx, camera) {
        if (!this.active) return;

        const screenX = this.x - camera.x + ctx.canvas.width / 2;
        const screenY = this.y - camera.y + ctx.canvas.height / 2;

        ctx.save();
        ctx.translate(screenX, screenY);
        ctx.rotate(this.angle);

        switch (this.type) {
            case 'cannon':
                this.renderCannon(ctx);
                break;
            case 'torpedo':
                this.renderTorpedo(ctx);
                break;
            case 'depthCharge':
                this.renderDepthCharge(ctx);
                break;
        }

        ctx.restore();
    }

    renderCannon(ctx) {
        ctx.fillStyle = '#333333';
        ctx.fillRect(-this.size/2, -this.size/2, this.size, this.size);
        
        ctx.fillStyle = '#666666';
        ctx.fillRect(-this.size/4, -this.size/4, this.size/2, this.size/2);
    }

    renderTorpedo(ctx) {
        // Draw homing indicator if active
        if (!this.owner.isAI && this.target && !this.target.isDead) {
            const distance = this.getDistanceToTarget(this.target);
            if (distance < this.homingRange) {
                // Draw a subtle line to target when homing
                ctx.strokeStyle = 'rgba(255, 100, 100, 0.3)';
                ctx.lineWidth = 1;
                ctx.setLineDash([5, 5]);
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(
                    (this.target.x - this.x) * 0.5, 
                    (this.target.y - this.y) * 0.5
                );
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
        
        // Torpedo body
        ctx.fillStyle = '#2c3e50';
        ctx.fillRect(-this.size, -this.size/3, this.size * 2, this.size * 0.66);
        
        // Torpedo tip
        ctx.fillStyle = '#34495e';
        ctx.beginPath();
        ctx.moveTo(this.size, 0);
        ctx.lineTo(this.size * 1.5, -this.size/3);
        ctx.lineTo(this.size * 1.5, this.size/3);
        ctx.closePath();
        ctx.fill();

        // Propeller
        ctx.fillStyle = '#7f8c8d';
        ctx.fillRect(-this.size * 1.2, -this.size/4, this.size * 0.4, this.size/2);
        
        // Draw a glowing effect when homing
        if (!this.owner.isAI && this.target && !this.target.isDead) {
            const distance = this.getDistanceToTarget(this.target);
            if (distance < this.homingRange) {
                ctx.shadowBlur = 10;
                ctx.shadowColor = '#ff6464';
                ctx.strokeStyle = 'rgba(255, 100, 100, 0.5)';
                ctx.lineWidth = 2;
                ctx.strokeRect(-this.size, -this.size/3, this.size * 2, this.size * 0.66);
                ctx.shadowBlur = 0;
            }
        }
    }

    renderDepthCharge(ctx) {
        ctx.fillStyle = '#1a1a1a';
        ctx.beginPath();
        ctx.arc(0, 0, this.size, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = '#333333';
        ctx.beginPath();
        ctx.arc(0, 0, this.size * 0.7, 0, Math.PI * 2);
        ctx.fill();
    }

    explode() {
        this.active = false;
        
        switch (this.type) {
            case 'cannon':
                particleSystem.createExplosion(this.x, this.y, 'small');
                break;
            case 'torpedo':
                particleSystem.createExplosion(this.x, this.y, 'medium');
                break;
            case 'depthCharge':
                particleSystem.createDepthChargeExplosion(this.x, this.y);
                break;
        }
    }
}

class Cannon extends Weapon {
    constructor(owner, x, y, angle) {
        super('cannon', owner);
        this.x = x;
        this.y = y;
        this.angle = angle;
        this.damage = 25;
        this.speed = 800;
        this.maxLifetime = 3;
        this.size = 4;
        
        this.vx = Math.cos(angle) * this.speed;
        this.vy = Math.sin(angle) * this.speed;

        particleSystem.createCannonMuzzleFlash(x, y, angle);
    }
}

class Torpedo extends Weapon {
    constructor(owner, x, y, angle) {
        super('torpedo', owner);
        this.x = x;
        this.y = y;
        this.angle = angle;
        this.damage = 75;
        this.speed = 400;
        this.maxLifetime = 8;
        this.size = 8;
        this.homingStrength = 0.3; // Homing strength (0 = no homing, 1 = perfect homing)
        this.homingRange = 300; // Range at which homing activates
        this.target = null;
        
        this.vx = Math.cos(angle) * this.speed;
        this.vy = Math.sin(angle) * this.speed;
    }

    update(deltaTime) {
        super.update(deltaTime);
        
        // Homing behavior
        if (!this.owner.isAI) {
            this.updateHoming(deltaTime);
        }
    }

    updateHoming(deltaTime) {
        // Find nearest enemy target
        if (!this.target || !this.target.isDead && this.getDistanceToTarget(this.target) > this.homingRange) {
            this.findNearestTarget();
        }

        if (this.target && !this.target.isDead) {
            const targetDistance = this.getDistanceToTarget(this.target);
            
            if (targetDistance < this.homingRange) {
                // Calculate angle to target
                const targetAngle = Math.atan2(
                    this.target.y - this.y,
                    this.target.x - this.x
                );
                
                // Smoothly adjust torpedo angle towards target
                let angleDiff = targetAngle - this.angle;
                
                // Normalize angle difference
                while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
                while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
                
                // Apply homing
                this.angle += angleDiff * this.homingStrength * deltaTime;
                
                // Update velocity to match new angle
                this.vx = Math.cos(this.angle) * this.speed;
                this.vy = Math.sin(this.angle) * this.speed;
            }
        }
    }

    findNearestTarget() {
        // This will be set by the game when torpedo is created
        if (this.owner.game && this.owner.game.targets) {
            let nearestTarget = null;
            let nearestDistance = this.homingRange;
            
            this.owner.game.targets.forEach(target => {
                if (target.isDead) return;
                
                const distance = this.getDistanceToTarget(target);
                if (distance < nearestDistance) {
                    nearestDistance = distance;
                    nearestTarget = target;
                }
            });
            
            this.target = nearestTarget;
        }
    }

    getDistanceToTarget(target) {
        const dx = target.x - this.x;
        const dy = target.y - this.y;
        return Math.sqrt(dx * dx + dy * dy);
    }
}

class DepthCharge extends Weapon {
    constructor(owner, x, y) {
        super('depthCharge', owner);
        this.x = x;
        this.y = y;
        this.angle = 0;
        this.damage = 50;
        this.speed = 100;
        this.maxLifetime = 10;
        this.size = 12;
        
        this.vx = (Math.random() - 0.5) * this.speed;
        this.vy = 50; // Sinks downward
    }
}

class WeaponSystem {
    constructor(ship) {
        this.ship = ship;
        this.selectedWeapon = 0;
        this.weapons = [];
        this.lastFireTime = 0;
        
        this.weaponData = {
            cannon: {
                ammo: Infinity,
                fireRate: 500,
                speed: 800,
                damage: 25,
                spread: 0.1
            },
            torpedo: {
                ammo: 8,
                fireRate: 2000,
                speed: 400,
                damage: 75,
                spread: 0.05
            },
            depthCharge: {
                ammo: 12,
                fireRate: 1500,
                speed: 100,
                damage: 50,
                spread: 0.2
            }
        };
    }

    selectWeapon(index) {
        if (index >= 0 && index < 3) {
            this.selectedWeapon = index;
            this.updateUI();
        }
    }

    fire(targetX, targetY) {
        const now = Date.now();
        const weaponTypes = ['cannon', 'torpedo', 'depthCharge'];
        const weaponType = weaponTypes[this.selectedWeapon];
        const weaponInfo = this.weaponData[weaponType];

        if (now - this.lastFireTime < weaponInfo.fireRate) {
            return;
        }

        if (weaponType === 'depthCharge') {
            if (weaponInfo.ammo === 0) return;
            this.fireDepthCharge();
        } else {
            const angle = Math.atan2(targetY - this.ship.y, targetX - this.ship.x);
            this.fireProjectile(weaponType, angle, weaponInfo);
        }

        this.lastFireTime = now;
        
        if (weaponInfo.ammo !== Infinity) {
            weaponInfo.ammo--;
            this.updateUI();
        }
    }

    fireProjectile(type, angle, weaponInfo) {
        const spread = (Math.random() - 0.5) * weaponInfo.spread;
        const finalAngle = angle + spread;
        
        const projectileX = this.ship.x + Math.cos(finalAngle) * 30;
        const projectileY = this.ship.y + Math.sin(finalAngle) * 30;

        let projectile;
        switch (type) {
            case 'cannon':
                projectile = new Cannon(this.ship, projectileX, projectileY, finalAngle);
                break;
            case 'torpedo':
                projectile = new Torpedo(this.ship, projectileX, projectileY, finalAngle);
                if (this.ship.game) {
                    projectile.game = this.ship.game;
                }
                break;
        }

        if (projectile) {
            this.weapons.push(projectile);
        }
    }

    fireDepthCharge() {
        const offsetX = (Math.random() - 0.5) * 20;
        const charge = new DepthCharge(this.ship, this.ship.x + offsetX, this.ship.y);
        this.weapons.push(charge);
    }

    update(deltaTime) {
        this.weapons = this.weapons.filter(weapon => {
            weapon.update(deltaTime);
            return weapon.active;
        });
    }

    render(ctx, camera) {
        this.weapons.forEach(weapon => {
            weapon.render(ctx, camera);
        });
    }

    updateUI() {
        document.querySelectorAll('.weapon-slot').forEach((slot, index) => {
            if (index === this.selectedWeapon) {
                slot.classList.add('active');
            } else {
                slot.classList.remove('active');
            }
        });

        const weaponTypes = ['cannon', 'torpedo', 'depthCharge'];
        const ammoElements = ['cannon-ammo', 'torpedo-ammo', 'depth-ammo'];
        
        weaponTypes.forEach((type, index) => {
            const ammoElement = document.getElementById(ammoElements[index]);
            if (ammoElement) {
                const ammo = this.weaponData[type].ammo;
                ammoElement.textContent = ammo === Infinity ? '∞' : ammo;
            }
        });
    }

    getWeaponInfo() {
        const weaponTypes = ['cannon', 'torpedo', 'depthCharge'];
        return this.weaponData[weaponTypes[this.selectedWeapon]];
    }

    clear() {
        this.weapons = [];
    }
}