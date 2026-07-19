/**
 * Particle System for Visual Effects
 * Creates explosions, smoke trails, water splashes, and other effects
 */

class Particle {
    constructor(x, y, color, game, isExplosion = false) {
        this.x = x;
        this.y = y;
        this.game = game;
        this.color = color;
        
        if (isExplosion) {
            // Explosion particles - radial burst
            const angle = Math.random() * Math.PI * 2;
            const speed = 100 + Math.random() * 200;
            this.vx = Math.cos(angle) * speed;
            this.vy = Math.sin(angle) * speed;
            this.life = 0.5 + Math.random() * 0.5;
            this.maxLife = this.life;
            this.size = 3 + Math.random() * 5;
            this.gravity = 50;
        } else {
            // Regular particles - slower, floaty
            this.vx = (Math.random() - 0.5) * 100;
            this.vy = (Math.random() - 0.5) * 100 - 50;
            this.life = 0.3 + Math.random() * 0.4;
            this.maxLife = this.life;
            this.size = 2 + Math.random() * 3;
            this.gravity = 20;
        }
        
        this.rotation = Math.random() * Math.PI * 2;
        this.rotationSpeed = (Math.random() - 0.5) * 5;
        this.drag = 0.98;
    }
    
    update(deltaTime) {
        // Apply velocity
        this.x += this.vx * deltaTime;
        this.y += this.vy * deltaTime;
        
        // Apply gravity
        this.vy += this.gravity * deltaTime;
        
        // Apply drag
        this.vx *= this.drag;
        this.vy *= this.drag;
        
        // Rotate
        this.rotation += this.rotationSpeed * deltaTime;
        
        // Decrease life
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = this.life / this.maxLife;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(this.x, this.y);
        ctx.rotate(this.rotation);
        
        // Parse color and add alpha
        if (this.color.startsWith('#')) {
            const r = parseInt(this.color.substr(1, 2), 16);
            const g = parseInt(this.color.substr(3, 2), 16);
            const b = parseInt(this.color.substr(5, 2), 16);
            ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
        } else {
            ctx.fillStyle = this.color;
        }
        
        // Draw particle as rectangle
        ctx.fillRect(-this.size / 2, -this.size / 2, this.size, this.size);
        
        ctx.restore();
    }
}

class SmokeParticle {
    constructor(x, y, game) {
        this.x = x;
        this.y = y;
        this.game = game;
        
        this.vx = (Math.random() - 0.5) * 30;
        this.vy = -20 - Math.random() * 30;
        this.life = 1 + Math.random() * 1;
        this.maxLife = this.life;
        this.size = 5 + Math.random() * 10;
        this.maxSize = this.size * 3;
        this.rotation = Math.random() * Math.PI * 2;
        this.rotationSpeed = (Math.random() - 0.5) * 2;
    }
    
    update(deltaTime) {
        this.x += this.vx * deltaTime;
        this.y += this.vy * deltaTime;
        
        // Smoke rises and expands
        this.vy -= 10 * deltaTime;
        this.size += (this.maxSize - this.size) * deltaTime;
        
        this.rotation += this.rotationSpeed * deltaTime;
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = (this.life / this.maxLife) * 0.4;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(this.x, this.y);
        ctx.rotate(this.rotation);
        
        // Gray smoke
        ctx.fillStyle = '#7f8c8d';
        ctx.beginPath();
        ctx.arc(0, 0, this.size, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.restore();
    }
}

class WaterSplash {
    constructor(x, y, game, intensity = 1) {
        this.x = x;
        this.y = y;
        this.game = game;
        this.intensity = intensity;
        
        const angle = Math.random() * Math.PI * 2;
        const speed = 50 * intensity + Math.random() * 100 * intensity;
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed - 50;
        
        this.life = 0.4 + Math.random() * 0.3;
        this.maxLife = this.life;
        this.size = 2 + Math.random() * 3 * intensity;
        this.gravity = 200;
    }
    
    update(deltaTime) {
        this.x += this.vx * deltaTime;
        this.y += this.vy * deltaTime;
        
        this.vy += this.gravity * deltaTime;
        this.vx *= 0.98;
        
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = this.life / this.maxLife;
        
        ctx.save();
        ctx.globalAlpha = alpha * 0.7;
        ctx.fillStyle = '#3498db';
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }
}

class BulletTracer {
    constructor(x1, y1, x2, y2, color, game) {
        this.x1 = x1;
        this.y1 = y1;
        this.x2 = x2;
        this.y2 = y2;
        this.color = color;
        this.game = game;
        this.life = 0.1;
        this.maxLife = this.life;
    }
    
    update(deltaTime) {
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = this.life / this.maxLife;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = this.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(this.x1, this.y1);
        ctx.lineTo(this.x2, this.y2);
        ctx.stroke();
        ctx.restore();
    }
}

class WakeParticle {
    constructor(x, y, angle, game) {
        this.x = x;
        this.y = y;
        this.game = game;
        
        // Wake particles move perpendicular to ship direction
        const spreadAngle = angle + (Math.random() - 0.5) * Math.PI / 3;
        const speed = 20 + Math.random() * 30;
        this.vx = Math.cos(spreadAngle) * speed;
        this.vy = Math.sin(spreadAngle) * speed;
        
        this.life = 0.5 + Math.random() * 0.5;
        this.maxLife = this.life;
        this.size = 3 + Math.random() * 4;
        this.maxSize = this.size * 2;
    }
    
    update(deltaTime) {
        this.x += this.vx * deltaTime;
        this.y += this.vy * deltaTime;
        
        // Slow down
        this.vx *= 0.95;
        this.vy *= 0.95;
        
        // Expand
        this.size += (this.maxSize - this.size) * deltaTime * 2;
        
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = (this.life / this.maxLife) * 0.5;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = '#ecf0f1';
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }
}

class MuzzleFlash {
    constructor(x, y, angle, game) {
        this.x = x;
        this.y = y;
        this.angle = angle;
        this.game = game;
        this.life = 0.08;
        this.maxLife = this.life;
        this.size = 15;
    }
    
    update(deltaTime) {
        this.life -= deltaTime;
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = this.life / this.maxLife;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(this.x, this.y);
        ctx.rotate(this.angle);
        
        // Yellow-white flash
        const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, this.size);
        gradient.addColorStop(0, '#fff');
        gradient.addColorStop(0.4, '#ffeb3b');
        gradient.addColorStop(1, 'rgba(255, 193, 7, 0)');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(-this.size, -this.size / 2, this.size * 2, this.size);
        
        ctx.restore();
    }
}

class ImpactEffect {
    constructor(x, y, game) {
        this.x = x;
        this.y = y;
        this.game = game;
        this.life = 0.2;
        this.maxLife = this.life;
        this.rings = [
            { radius: 5, maxRadius: 30, alpha: 1 },
            { radius: 3, maxRadius: 25, alpha: 0.7 },
            { radius: 1, maxRadius: 20, alpha: 0.5 }
        ];
    }
    
    update(deltaTime) {
        this.life -= deltaTime;
        
        // Expand rings
        for (const ring of this.rings) {
            ring.radius += (ring.maxRadius - ring.radius) * deltaTime * 10;
        }
    }
    
    render(ctx) {
        if (this.life <= 0) return;
        
        const alpha = this.life / this.maxLife;
        
        ctx.save();
        ctx.globalAlpha = alpha;
        
        for (const ring of this.rings) {
            ctx.strokeStyle = '#f39c12';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(this.x, this.y, ring.radius, 0, Math.PI * 2);
            ctx.stroke();
        }
        
        ctx.restore();
    }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        Particle,
        SmokeParticle,
        WaterSplash,
        BulletTracer,
        WakeParticle,
        MuzzleFlash,
        ImpactEffect
    };
}