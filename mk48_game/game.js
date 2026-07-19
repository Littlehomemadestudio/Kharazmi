class Game {
    constructor() {
        this.canvas = document.getElementById('gameCanvas');
        this.ctx = this.canvas.getContext('2d');
        this.isRunning = false;
        this.isPaused = false;
        this.lastTime = 0;
        
        this.worldSize = 2000;
        this.camera = { x: 0, y: 0 };
        
        this.playerShip = null;
        this.targets = [];
        this.crates = [];
        this.weapons = [];
        
        this.mouse = { x: 0, y: 0, isDown: false };
        this.keys = {};
        
        this.setupCanvas();
        this.setupEventListeners();
        
        // Make game globally available for UI
        window.game = this;
    }

    setupCanvas() {
        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());
    }

    resizeCanvas() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    setupEventListeners() {
        // Mouse controls
        this.canvas.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });

        this.canvas.addEventListener('mousedown', (e) => {
            this.mouse.isDown = true;
            this.handleFire();
        });

        this.canvas.addEventListener('mouseup', (e) => {
            this.mouse.isDown = false;
        });

        // Keyboard controls
        window.addEventListener('keydown', (e) => {
            this.keys[e.key.toLowerCase()] = true;
            this.handleInput();
        });

        window.addEventListener('keyup', (e) => {
            this.keys[e.key.toLowerCase()] = false;
            this.handleInput();
        });

        // Prevent context menu on right click
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });
    }

    startGame(shipType, mode) {
        this.gameMode = mode;
        this.initializeWorld(shipType);
        this.isRunning = true;
        this.isPaused = false;
        this.lastTime = performance.now();
        this.gameLoop();
    }

    initializeWorld(shipType) {
        // Clear existing entities
        this.targets = [];
        this.crates = [];
        this.weapons = [];
        
        // Create player ship
        this.playerShip = new Ship(shipType, 0, 0);
        this.playerShip.game = this;
        
        // Create targets based on game mode
        this.createTargets();
        
        // Create crates
        this.createCrates();
        
        // Reset camera
        this.camera.x = this.playerShip.x;
        this.camera.y = this.playerShip.y;
    }

    createTargets() {
        const targetCount = this.gameMode === 'survival' ? 15 : 8;
        
        for (let i = 0; i < targetCount; i++) {
            const angle = (Math.PI * 2 * i) / targetCount;
            const distance = 300 + Math.random() * 500;
            
            const x = Math.cos(angle) * distance;
            const y = Math.sin(angle) * distance;
            
            const types = ['destroyer', 'cruiser', 'corvette'];
            const type = types[Math.floor(Math.random() * types.length)];
            
            const target = new Ship(type, x, y);
            target.isAI = true;
            target.health *= 0.7; // AI targets have less health
            target.maxHealth = target.health;
            
            this.targets.push(target);
        }
    }

    createCrates() {
        const crateCount = 20;
        
        for (let i = 0; i < crateCount; i++) {
            const angle = Math.random() * Math.PI * 2;
            const distance = 200 + Math.random() * 800;
            
            this.crates.push({
                x: Math.cos(angle) * distance,
                y: Math.sin(angle) * distance,
                size: 15,
                collected: false,
                type: Math.random() < 0.7 ? 'health' : 'ammo',
                value: Math.random() < 0.7 ? 25 : 50
            });
        }
    }

    handleInput() {
        if (!this.playerShip || this.isPaused) return;

        const input = {
            forward: this.keys['w'],
            backward: this.keys['s'],
            left: this.keys['a'],
            right: this.keys['d']
        };

        this.playerShip.setInput(input);
    }

    handleFire() {
        if (!this.playerShip || this.isPaused) return;
        
        // Convert mouse position to world coordinates
        const worldX = this.mouse.x - this.canvas.width / 2 + this.camera.x;
        const worldY = this.mouse.y - this.canvas.height / 2 + this.camera.y;
        
        this.playerShip.fireWeapon(worldX, worldY);
    }

    updateAI(deltaTime) {
        this.targets.forEach(target => {
            if (target.isDead) return;

            // Simple AI behavior
            const dx = this.playerShip.x - target.x;
            const dy = this.playerShip.y - target.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < 400) {
                // Attack player
                const targetAngle = Math.atan2(dy, dx);
                const angleDiff = targetAngle - target.angle;
                
                // Normalize angle difference
                let normalizedDiff = angleDiff;
                while (normalizedDiff > Math.PI) normalizedDiff -= Math.PI * 2;
                while (normalizedDiff < -Math.PI) normalizedDiff += Math.PI * 2;
                
                // Turn towards player
                if (Math.abs(normalizedDiff) > 0.1) {
                    target.input.left = normalizedDiff < 0;
                    target.input.right = normalizedDiff > 0;
                } else {
                    target.input.left = false;
                    target.input.right = false;
                    
                    // Fire if aligned
                    if (Math.random() < 0.02 && distance < 300) {
                        target.fireWeapon(this.playerShip.x, this.playerShip.y);
                    }
                }
                
                // Move towards or away based on distance
                if (distance > 200) {
                    target.input.forward = true;
                    target.input.backward = false;
                } else if (distance < 150) {
                    target.input.forward = false;
                    target.input.backward = true;
                }
            } else {
                // Wander randomly
                if (Math.random() < 0.02) {
                    target.input.forward = Math.random() < 0.7;
                    target.input.left = Math.random() < 0.3;
                    target.input.right = Math.random() < 0.3;
                }
            }
            
            target.update(deltaTime);
        });
    }

    checkCollisions() {
        if (!this.playerShip || this.playerShip.isDead) return;

        // Check weapon collisions
        const allWeapons = [
            ...this.playerShip.weaponSystem.weapons,
            ...this.targets.flatMap(t => t.weaponSystem.weapons)
        ];

        allWeapons.forEach(weapon => {
            // Check collision with player
            if (weapon.owner !== this.playerShip && !weapon.owner.isDead) {
                const dx = weapon.x - this.playerShip.x;
                const dy = weapon.y - this.playerShip.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance < this.playerShip.getHitboxSize() + weapon.size) {
                    const isDead = this.playerShip.takeDamage(weapon.damage);
                    weapon.explode();
                    
                    if (isDead) {
                        this.endGame();
                    }
                }
            }
            
            // Check collision with targets
            if (weapon.owner === this.playerShip) {
                this.targets.forEach(target => {
                    if (target.isDead) return;
                    
                    const dx = weapon.x - target.x;
                    const dy = weapon.y - target.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distance < target.getHitboxSize() + weapon.size) {
                        const isDead = target.takeDamage(weapon.damage);
                        weapon.explode();
                        
                        if (isDead) {
                            uiManager.addScore(250);
                            this.playerShip.addXP(25); // XP for destroying enemy
                            uiManager.updateXP(this.playerShip.getXPProgress());
                            this.respawnTarget(target);
                        }
                    }
                });
            }
        });

        // Check crate collection
        this.crates.forEach(crate => {
            if (crate.collected) return;
            
            const dx = crate.x - this.playerShip.x;
            const dy = crate.y - this.playerShip.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < this.playerShip.getHitboxSize() + crate.size) {
                crate.collected = true;
                
                // Grant XP for collecting crate
                const xpGained = crate.type === 'health' ? 10 : 15;
                this.playerShip.addXP(xpGained);
                
                if (crate.type === 'health') {
                    this.playerShip.heal(crate.value);
                } else {
                    // Restore ammo
                    const weaponSystem = this.playerShip.weaponSystem;
                    weaponSystem.weaponData.torpedo.ammo = Math.min(
                        weaponSystem.weaponData.torpedo.ammo + 4, 8
                    );
                    weaponSystem.weaponData.depthCharge.ammo = Math.min(
                        weaponSystem.weaponData.depthCharge.ammo + 6, 12
                    );
                    weaponSystem.updateUI();
                }
                
                uiManager.addCrate();
                uiManager.updateXP(this.playerShip.getXPProgress());
                this.respawnCrate(crate);
            }
        });

        // Check ship-to-ship collisions
        this.targets.forEach(target => {
            if (target.isDead) return;
            
            const dx = target.x - this.playerShip.x;
            const dy = target.y - this.playerShip.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < this.playerShip.getHitboxSize() + target.getHitboxSize()) {
                // Collision damage to both ships
                this.playerShip.takeDamage(20);
                target.takeDamage(20);
                
                // Push ships apart
                const pushForce = 50;
                const pushX = (dx / distance) * pushForce;
                const pushY = (dy / distance) * pushForce;
                
                this.playerShip.velocity.x -= pushX;
                this.playerShip.velocity.y -= pushY;
                target.velocity.x += pushX;
                target.velocity.y += pushY;
                
                particleSystem.createWaterSplash(
                    (this.playerShip.x + target.x) / 2,
                    (this.playerShip.y + target.y) / 2,
                    'medium'
                );
            }
        });
    }

    respawnTarget(target) {
        // Respawn target at new location
        const angle = Math.random() * Math.PI * 2;
        const distance = 400 + Math.random() * 600;
        
        target.x = Math.cos(angle) * distance;
        target.y = Math.sin(angle) * distance;
        target.health = target.maxHealth;
        target.isDead = false;
        target.weaponSystem.clear();
    }

    respawnCrate(crate) {
        // Respawn crate at new location
        const angle = Math.random() * Math.PI * 2;
        const distance = 200 + Math.random() * 800;
        
        crate.x = Math.cos(angle) * distance;
        crate.y = Math.sin(angle) * distance;
        crate.collected = false;
        crate.type = Math.random() < 0.7 ? 'health' : 'ammo';
        crate.value = Math.random() < 0.7 ? 25 : 50;
    }

    updateCamera() {
        if (!this.playerShip) return;
        
        // Smooth camera follow
        const smoothing = 0.1;
        this.camera.x += (this.playerShip.x - this.camera.x) * smoothing;
        this.camera.y += (this.playerShip.y - this.camera.y) * smoothing;
    }

    render() {
        // Clear canvas
        this.ctx.fillStyle = '#1a2332';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Render water grid
        this.renderWaterGrid();

        // Render crates
        this.renderCrates();

        // Render targets
        this.targets.forEach(target => {
            target.render(this.ctx, this.camera);
        });

        // Render player
        if (this.playerShip) {
            this.playerShip.render(this.ctx, this.camera);
        }

        // Render particles
        particleSystem.render(this.ctx, this.camera);

        // Update minimap
        if (this.playerShip && uiManager.getGameState() === 'playing') {
            uiManager.updateMinimap(this.playerShip, this.targets, this.crates, this.worldSize);
        }
    }

    renderWaterGrid() {
        const gridSize = 50;
        const offsetX = -this.camera.x % gridSize;
        const offsetY = -this.camera.y % gridSize;
        
        this.ctx.strokeStyle = 'rgba(74, 144, 226, 0.1)';
        this.ctx.lineWidth = 1;
        
        // Draw vertical lines
        for (let x = offsetX; x < this.canvas.width; x += gridSize) {
            this.ctx.beginPath();
            this.ctx.moveTo(x, 0);
            this.ctx.lineTo(x, this.canvas.height);
            this.ctx.stroke();
        }
        
        // Draw horizontal lines
        for (let y = offsetY; y < this.canvas.height; y += gridSize) {
            this.ctx.beginPath();
            this.ctx.moveTo(0, y);
            this.ctx.lineTo(this.canvas.width, y);
            this.ctx.stroke();
        }
    }

    renderCrates() {
        this.crates.forEach(crate => {
            if (crate.collected) return;
            
            const screenX = crate.x - this.camera.x + this.canvas.width / 2;
            const screenY = crate.y - this.camera.y + this.canvas.height / 2;
            
            // Don't render if off-screen
            if (screenX < -50 || screenX > this.canvas.width + 50 ||
                screenY < -50 || screenY > this.canvas.height + 50) {
                return;
            }
            
            this.ctx.save();
            this.ctx.translate(screenX, screenY);
            
            // Pulsing effect
            const pulse = Math.sin(Date.now() * 0.003) * 0.2 + 1;
            this.ctx.scale(pulse, pulse);
            
            // Draw crate
            const color = crate.type === 'health' ? '#2ecc71' : '#f39c12';
            this.ctx.fillStyle = color;
            this.ctx.fillRect(-crate.size/2, -crate.size/2, crate.size, crate.size);
            
            // Draw crate icon
            this.ctx.fillStyle = 'white';
            this.ctx.font = '12px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            const icon = crate.type === 'health' ? '+' : '⚡';
            this.ctx.fillText(icon, 0, 0);
            
            this.ctx.restore();
        });
    }

    gameLoop(currentTime = 0) {
        if (!this.isRunning) return;
        
        const deltaTime = Math.min((currentTime - this.lastTime) / 1000, 0.1);
        this.lastTime = currentTime;
        
        if (!this.isPaused && uiManager.getGameState() === 'playing') {
            // Update game state
            if (this.playerShip) {
                this.playerShip.update(deltaTime);
                
                // Update UI
                uiManager.updateHealth(this.playerShip.health, this.playerShip.maxHealth);
                uiManager.updateWeaponUI(this.playerShip.weaponSystem);
                uiManager.updateXP(this.playerShip.getXPProgress());
            }
            
            this.updateAI(deltaTime);
            particleSystem.update();
            this.checkCollisions();
            this.updateCamera();
            
            // Auto-fire if mouse is down
            if (this.mouse.isDown) {
                this.handleFire();
            }
        }
        
        // Render everything
        this.render();
        
        requestAnimationFrame((time) => this.gameLoop(time));
    }

    endGame() {
        this.isRunning = false;
        uiManager.showGameOver(uiManager.score);
    }
}

// Initialize game when page loads
window.addEventListener('load', () => {
    const game = new Game();
});