class ParticleSystem {
    constructor() {
        this.particles = [];
        this.waterWaves = [];
    }

    createExplosion(x, y, size = 'medium') {
        const particleCount = size === 'large' ? 30 : size === 'small' ? 10 : 20;
        const colors = ['#ff6b35', '#ff9558', '#ffd93d', '#ffffff'];
        
        for (let i = 0; i < particleCount; i++) {
            const angle = (Math.PI * 2 * i) / particleCount;
            const speed = 2 + Math.random() * 4;
            
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                size: 2 + Math.random() * 4,
                color: colors[Math.floor(Math.random() * colors.length)],
                life: 1.0,
                decay: 0.02 + Math.random() * 0.02,
                type: 'explosion'
            });
        }

        // Create water splash
        this.createWaterSplash(x, y, size);
    }

    createWaterSplash(x, y, size = 'medium') {
        const waveCount = size === 'large' ? 15 : size === 'small' ? 5 : 10;
        
        for (let i = 0; i < waveCount; i++) {
            const angle = (Math.PI * 2 * i) / waveCount;
            const speed = 1 + Math.random() * 2;
            
            this.waterWaves.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                radius: 5 + Math.random() * 10,
                maxRadius: 20 + Math.random() * 30,
                life: 1.0,
                decay: 0.015 + Math.random() * 0.01
            });
        }
    }

    createTorpedoTrail(x, y) {
        this.particles.push({
            x: x,
            y: y,
            vx: (Math.random() - 0.5) * 0.5,
            vy: (Math.random() - 0.5) * 0.5,
            size: 3 + Math.random() * 2,
            color: '#4a90e2',
            life: 0.8,
            decay: 0.04,
            type: 'trail'
        });
    }

    createCannonMuzzleFlash(x, y, angle) {
        for (let i = 0; i < 5; i++) {
            const spread = (Math.random() - 0.5) * 0.3;
            const particleAngle = angle + spread;
            const speed = 3 + Math.random() * 3;
            
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(particleAngle) * speed,
                vy: Math.sin(particleAngle) * speed,
                size: 2 + Math.random() * 3,
                color: '#ffff99',
                life: 0.5,
                decay: 0.1,
                type: 'muzzle'
            });
        }
    }

    createDepthChargeExplosion(x, y) {
        // Underwater explosion effect
        const bubbleCount = 25;
        
        for (let i = 0; i < bubbleCount; i++) {
            const angle = (Math.PI * 2 * i) / bubbleCount;
            const speed = 1 + Math.random() * 3;
            
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 1, // Bubbles rise
                size: 1 + Math.random() * 3,
                color: 'rgba(255, 255, 255, 0.6)',
                life: 1.0,
                decay: 0.01 + Math.random() * 0.02,
                type: 'bubble'
            });
        }

        // Water surface disturbance
        this.createWaterSplash(x, y, 'large');
    }

    createWake(x, y, shipAngle) {
        // Create ship wake particles
        const perpAngle = shipAngle + Math.PI / 2;
        
        for (let i = -1; i <= 1; i++) {
            this.waterWaves.push({
                x: x + Math.cos(perpAngle) * i * 10,
                y: y + Math.sin(perpAngle) * i * 10,
                vx: -Math.cos(shipAngle) * 0.5,
                vy: -Math.sin(shipAngle) * 0.5,
                radius: 3,
                maxRadius: 15,
                life: 0.6,
                decay: 0.02
            });
        }
    }

    createLevelUpEffect(x, y) {
        // Create golden sparkles for level up
        for (let i = 0; i < 20; i++) {
            const angle = (Math.PI * 2 * i) / 20;
            const speed = 1 + Math.random() * 3;
            
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 1, // Slight upward bias
                size: 3 + Math.random() * 3,
                color: '#ffd700',
                life: 1.0,
                decay: 0.015 + Math.random() * 0.01,
                type: 'levelup'
            });
        }

        // Create expanding golden rings
        for (let i = 0; i < 3; i++) {
            setTimeout(() => {
                this.waterWaves.push({
                    x: x,
                    y: y,
                    vx: 0,
                    vy: 0,
                    radius: 10,
                    maxRadius: 50 + i * 20,
                    life: 1.0,
                    decay: 0.02,
                    color: '#ffd700'
                });
            }, i * 100);
        }
    }

    update() {
        // Update explosion particles
        this.particles = this.particles.filter(particle => {
            particle.x += particle.vx;
            particle.y += particle.vy;
            particle.life -= particle.decay;
            
            if (particle.type === 'trail') {
                particle.vx *= 0.98;
                particle.vy *= 0.98;
            } else if (particle.type === 'bubble') {
                particle.vy -= 0.1; // Bubbles rise
                particle.vx *= 0.95;
            }
            
            return particle.life > 0;
        });

        // Update water waves
        this.waterWaves = this.waterWaves.filter(wave => {
            wave.x += wave.vx;
            wave.y += wave.vy;
            wave.life -= wave.decay;
            wave.radius = wave.maxRadius * (1 - wave.life);
            
            wave.vx *= 0.98;
            wave.vy *= 0.98;
            
            return wave.life > 0;
        });
    }

    render(ctx, camera) {
        // Render water waves
        this.waterWaves.forEach(wave => {
            ctx.save();
            ctx.globalAlpha = wave.life * 0.3;
            ctx.strokeStyle = wave.color || '#6ba3f5';
            ctx.lineWidth = wave.color ? 3 : 2;
            
            const screenX = wave.x - camera.x + ctx.canvas.width / 2;
            const screenY = wave.y - camera.y + ctx.canvas.height / 2;
            
            ctx.beginPath();
            ctx.arc(screenX, screenY, wave.radius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
        });

        // Render particles
        this.particles.forEach(particle => {
            ctx.save();
            ctx.globalAlpha = particle.life;
            
            const screenX = particle.x - camera.x + ctx.canvas.width / 2;
            const screenY = particle.y - camera.y + ctx.canvas.height / 2;
            
            if (particle.type === 'muzzle') {
                // Muzzle flash glow effect
                const gradient = ctx.createRadialGradient(screenX, screenY, 0, screenX, screenY, particle.size * 2);
                gradient.addColorStop(0, particle.color);
                gradient.addColorStop(1, 'transparent');
                ctx.fillStyle = gradient;
                ctx.fillRect(screenX - particle.size * 2, screenY - particle.size * 2, particle.size * 4, particle.size * 4);
            } else {
                ctx.fillStyle = particle.color;
                ctx.beginPath();
                ctx.arc(screenX, screenY, particle.size, 0, Math.PI * 2);
                ctx.fill();
            }
            
            ctx.restore();
        });
    }

    clear() {
        this.particles = [];
        this.waterWaves = [];
    }
}

// Global particle system instance
const particleSystem = new ParticleSystem();