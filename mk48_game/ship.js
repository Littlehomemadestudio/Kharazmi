class Ship {
    constructor(type, x, y) {
        this.type = type;
        this.x = x;
        this.y = y;
        this.angle = 0;
        this.velocity = { x: 0, y: 0 };
        this.angularVelocity = 0;
        
        this.setupShipStats();
        this.health = this.maxHealth;
        this.weaponSystem = new WeaponSystem(this);
        
        this.input = {
            forward: false,
            backward: false,
            left: false,
            right: false
        };
        
        this.lastWakeTime = 0;
        this.isDead = false;
        
        // Level and XP system (only for player)
        if (!this.isAI) {
            this.level = 1;
            this.xp = 0;
            this.xpToNextLevel = 100;
            this.shipLevel = 0; // 0: ship.png, 1: ship1.png, 2: ship2.png
            this.updateShipImage();
        }
    }

    setupShipStats() {
        switch (this.type) {
            case 'destroyer':
                this.size = 45;
                this.maxHealth = 100;
                this.speed = 200;
                this.turnSpeed = 2;
                this.acceleration = 150;
                this.friction = 0.95;
                this.color = '#4a90e2';
                this.imageDimensions = { width: 90, height: 18 };
                this.hitboxDimensions = { width: 45, height: 9 };
                break;
            case 'cruiser':
                this.size = 60;
                this.maxHealth = 150;
                this.speed = 150;
                this.turnSpeed = 1.5;
                this.acceleration = 100;
                this.friction = 0.92;
                this.color = '#2ecc71';
                this.imageDimensions = { width: 120, height: 24 };
                this.hitboxDimensions = { width: 60, height: 12 };
                break;
            case 'corvette':
                this.size = 30;
                this.maxHealth = 75;
                this.speed = 250;
                this.turnSpeed = 3;
                this.acceleration = 200;
                this.friction = 0.96;
                this.color = '#e74c3c';
                this.imageDimensions = { width: 60, height: 12 };
                this.hitboxDimensions = { width: 30, height: 6 };
                break;
            default:
                this.size = 45;
                this.maxHealth = 100;
                this.speed = 200;
                this.turnSpeed = 2;
                this.acceleration = 150;
                this.friction = 0.95;
                this.color = '#4a90e2';
                this.imageDimensions = { width: 90, height: 18 };
                this.hitboxDimensions = { width: 45, height: 9 };
        }
    }

    update(deltaTime) {
        if (this.isDead) return;

        this.handleInput(deltaTime);
        this.updatePhysics(deltaTime);
        this.updateEffects(deltaTime);
        this.weaponSystem.update(deltaTime);
    }

    handleInput(deltaTime) {
        // Rotation
        if (this.input.left) {
            this.angularVelocity = -this.turnSpeed;
        } else if (this.input.right) {
            this.angularVelocity = this.turnSpeed;
        } else {
            this.angularVelocity *= 0.9;
        }

        // Forward/Backward movement
        if (this.input.forward) {
            const thrust = this.acceleration * deltaTime;
            this.velocity.x += Math.cos(this.angle) * thrust;
            this.velocity.y += Math.sin(this.angle) * thrust;
        }
        
        if (this.input.backward) {
            const thrust = this.acceleration * deltaTime * 0.5;
            this.velocity.x -= Math.cos(this.angle) * thrust;
            this.velocity.y -= Math.sin(this.angle) * thrust;
        }
    }

    updatePhysics(deltaTime) {
        // Apply friction
        this.velocity.x *= this.friction;
        this.velocity.y *= this.friction;

        // Limit speed
        const currentSpeed = Math.sqrt(this.velocity.x ** 2 + this.velocity.y ** 2);
        if (currentSpeed > this.speed) {
            const scale = this.speed / currentSpeed;
            this.velocity.x *= scale;
            this.velocity.y *= scale;
        }

        // Update position
        this.x += this.velocity.x * deltaTime;
        this.y += this.velocity.y * deltaTime;

        // Update rotation
        this.angle += this.angularVelocity * deltaTime;
    }

    updateEffects(deltaTime) {
        const now = Date.now();
        const currentSpeed = Math.sqrt(this.velocity.x ** 2 + this.velocity.y ** 2);
        
        // Create wake effect
        if (currentSpeed > 50 && now - this.lastWakeTime > 200) {
            particleSystem.createWake(this.x, this.y, this.angle);
            this.lastWakeTime = now;
        }
    }

    takeDamage(damage) {
        this.health -= damage;
        
        if (this.health <= 0) {
            this.health = 0;
            this.isDead = true;
            particleSystem.createExplosion(this.x, this.y, 'large');
        } else {
            particleSystem.createWaterSplash(this.x, this.y, 'small');
        }
        
        return this.isDead;
    }

    heal(amount) {
        this.health = Math.min(this.health + amount, this.maxHealth);
    }

    fireWeapon(targetX, targetY) {
        if (!this.isDead) {
            this.weaponSystem.fire(targetX, targetY);
        }
    }

    selectWeapon(index) {
        this.weaponSystem.selectWeapon(index);
    }

    render(ctx, camera) {
        if (this.isDead) return;

        const screenX = this.x - camera.x + ctx.canvas.width / 2;
        const screenY = this.y - camera.y + ctx.canvas.height / 2;

        // Check if this is the player ship and has custom image
        if (!this.isAI && this.imageLoaded && this.shipImage) {
            ctx.save();
            ctx.translate(screenX, screenY);
            ctx.rotate(this.angle);
            
            // Draw the custom ship image with proper aspect ratio
            ctx.drawImage(this.shipImage, 
                -this.imageDimensions.width/2, 
                -this.imageDimensions.height/2, 
                this.imageDimensions.width, 
                this.imageDimensions.height);
            
            // Draw health bar if needed
            if (this.health < this.maxHealth) {
                this.drawHealthBar(ctx);
            }
            
            ctx.restore();
        } else {
            // Default ship rendering for AI ships or before image loads
            ctx.save();
            ctx.translate(screenX, screenY);
            ctx.rotate(this.angle);

            // Draw ship shadow
            ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
            this.drawShipShape(ctx, 3, 2);

            // Draw ship body
            ctx.fillStyle = this.color;
            this.drawShipShape(ctx, 0, 0);

            // Draw ship details
            this.drawShipDetails(ctx);

            // Draw health bar
            if (this.health < this.maxHealth) {
                this.drawHealthBar(ctx);
            }

            ctx.restore();
        }

        // Render weapons
        this.weaponSystem.render(ctx, camera);
    }

    drawShipShape(ctx, offsetX, offsetY) {
        ctx.translate(offsetX, offsetY);

        switch (this.type) {
            case 'destroyer':
                this.drawDestroyerShape(ctx);
                break;
            case 'cruiser':
                this.drawCruiserShape(ctx);
                break;
            case 'corvette':
                this.drawCorvetteShape(ctx);
                break;
            default:
                this.drawDefaultShape(ctx);
        }

        ctx.translate(-offsetX, -offsetY);
    }

    drawDestroyerShape(ctx) {
        // Main hull
        ctx.beginPath();
        ctx.moveTo(-this.size, -this.size * 0.3);
        ctx.lineTo(this.size * 0.8, -this.size * 0.4);
        ctx.lineTo(this.size, 0);
        ctx.lineTo(this.size * 0.8, this.size * 0.4);
        ctx.lineTo(-this.size, this.size * 0.3);
        ctx.closePath();
        ctx.fill();

        // Superstructure
        ctx.fillStyle = '#2c3e50';
        ctx.fillRect(-this.size * 0.3, -this.size * 0.2, this.size * 0.4, this.size * 0.4);

        // Bridge
        ctx.fillStyle = '#34495e';
        ctx.fillRect(-this.size * 0.1, -this.size * 0.3, this.size * 0.2, this.size * 0.2);
    }

    drawCruiserShape(ctx) {
        // Main hull
        ctx.beginPath();
        ctx.moveTo(-this.size, -this.size * 0.4);
        ctx.lineTo(this.size * 0.7, -this.size * 0.5);
        ctx.lineTo(this.size, 0);
        ctx.lineTo(this.size * 0.7, this.size * 0.5);
        ctx.lineTo(-this.size, this.size * 0.4);
        ctx.closePath();
        ctx.fill();

        // Superstructure
        ctx.fillStyle = '#27ae60';
        ctx.fillRect(-this.size * 0.4, -this.size * 0.3, this.size * 0.5, this.size * 0.6);

        // Bridge
        ctx.fillStyle = '#229954';
        ctx.fillRect(-this.size * 0.15, -this.size * 0.4, this.size * 0.3, this.size * 0.3);

        // Gun turret
        ctx.fillStyle = '#1e8449';
        ctx.fillRect(this.size * 0.3, -this.size * 0.1, this.size * 0.3, this.size * 0.2);
    }

    drawCorvetteShape(ctx) {
        // Main hull (sleek and fast)
        ctx.beginPath();
        ctx.moveTo(-this.size, -this.size * 0.2);
        ctx.lineTo(this.size * 0.9, -this.size * 0.25);
        ctx.lineTo(this.size, 0);
        ctx.lineTo(this.size * 0.9, this.size * 0.25);
        ctx.lineTo(-this.size, this.size * 0.2);
        ctx.closePath();
        ctx.fill();

        // Small superstructure
        ctx.fillStyle = '#c0392b';
        ctx.fillRect(-this.size * 0.2, -this.size * 0.15, this.size * 0.3, this.size * 0.3);

        // Bridge
        ctx.fillStyle = '#a93226';
        ctx.fillRect(-this.size * 0.05, -this.size * 0.2, this.size * 0.15, this.size * 0.15);
    }

    drawDefaultShape(ctx) {
        // Basic ship shape
        ctx.beginPath();
        ctx.moveTo(-this.size, -this.size * 0.3);
        ctx.lineTo(this.size * 0.8, -this.size * 0.4);
        ctx.lineTo(this.size, 0);
        ctx.lineTo(this.size * 0.8, this.size * 0.4);
        ctx.lineTo(-this.size, this.size * 0.3);
        ctx.closePath();
        ctx.fill();
    }

    drawShipDetails(ctx) {
        // Draw ship details based on type
        ctx.fillStyle = '#7f8c8d';
        
        switch (this.type) {
            case 'destroyer':
                // Forward gun
                ctx.fillRect(this.size * 0.5, -this.size * 0.1, this.size * 0.3, this.size * 0.2);
                // Rear gun
                ctx.fillRect(-this.size * 0.7, -this.size * 0.08, this.size * 0.2, this.size * 0.16);
                break;
            case 'cruiser':
                // Multiple gun positions
                ctx.fillRect(this.size * 0.6, -this.size * 0.15, this.size * 0.25, this.size * 0.3);
                ctx.fillRect(-this.size * 0.8, -this.size * 0.12, this.size * 0.25, this.size * 0.24);
                break;
            case 'corvette':
                // Single forward gun
                ctx.fillRect(this.size * 0.7, -this.size * 0.08, this.size * 0.2, this.size * 0.16);
                break;
        }
    }

    drawHealthBar(ctx) {
        const barWidth = this.imageDimensions ? this.imageDimensions.width : this.size * 2;
        const barHeight = 4;
        const barY = -(this.imageDimensions ? this.imageDimensions.height/2 : this.size) - 10;

        // Background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(-barWidth/2, barY, barWidth, barHeight);

        // Health fill
        const healthPercent = this.health / this.maxHealth;
        const healthColor = healthPercent > 0.5 ? '#2ecc71' : 
                           healthPercent > 0.25 ? '#f39c12' : '#e74c3c';
        
        ctx.fillStyle = healthColor;
        ctx.fillRect(-barWidth/2, barY, barWidth * healthPercent, barHeight);

        // Border
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.lineWidth = 1;
        ctx.strokeRect(-barWidth/2, barY, barWidth, barHeight);
    }

    setInput(input) {
        this.input = { ...this.input, ...input };
    }

    getHealthPercent() {
        return this.health / this.maxHealth;
    }

    getHitboxSize() {
        if (this.hitboxDimensions) {
            return Math.max(this.hitboxDimensions.width, this.hitboxDimensions.height) / 2;
        }
        return this.size;
    }

    getActualHitboxDimensions() {
        if (this.hitboxDimensions) {
            return this.hitboxDimensions;
        }
        return { width: this.size * 2, height: this.size * 2 };
    }

    addXP(amount) {
        if (this.isAI) return;
        
        this.xp += amount;
        
        // Check for level up
        while (this.xp >= this.xpToNextLevel) {
            this.levelUp();
        }
    }

    levelUp() {
        this.xp -= this.xpToNextLevel;
        this.level++;
        this.xpToNextLevel = Math.floor(this.xpToNextLevel * 1.5);
        
        // Upgrade ship every 3 levels
        if (this.level % 3 === 0 && this.shipLevel < 2) {
            this.shipLevel++;
            this.updateShipImage();
        }
        
        // Improve stats
        this.maxHealth += 10;
        this.health = Math.min(this.health + 20, this.maxHealth);
        this.speed += 5;
        this.turnSpeed += 0.1;
        
        // Create level up effect
        particleSystem.createLevelUpEffect(this.x, this.y);
    }

    updateShipImage() {
        if (this.isAI) return;
        
        this.shipImage = new Image();
        this.imageLoaded = false;
        
        const shipImages = ['ship.png', 'ship1.png', 'ship2.png'];
        this.shipImage.src = shipImages[this.shipLevel];
        
        this.shipImage.onload = () => {
            this.imageLoaded = true;
        };
    }

    getXPProgress() {
        return {
            current: this.xp,
            required: this.xpToNextLevel,
            level: this.level,
            progress: this.xp / this.xpToNextLevel
        };
    }
}