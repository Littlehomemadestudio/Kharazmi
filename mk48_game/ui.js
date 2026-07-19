class UIManager {
    constructor() {
        this.gameState = 'menu';
        this.selectedShip = null;
        this.score = 0;
        this.crates = 0;
        this.level = 1;
        this.gameMode = '';
        
        // Initialize XP display
        this.updateXP({
            current: 0,
            required: 100,
            level: 1,
            progress: 0
        });
        
        this.setupEventListeners();
        this.hideAllUI();
        this.showStartMenu();
    }

    setupEventListeners() {
        // Ship selection
        document.querySelectorAll('.ship-card').forEach(card => {
            card.addEventListener('click', (e) => {
                document.querySelectorAll('.ship-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                this.selectedShip = card.dataset.ship;
            });
        });

        // Keyboard controls
        document.addEventListener('keydown', (e) => {
            if (this.gameState === 'playing') {
                switch(e.key.toLowerCase()) {
                    case 'escape':
                        this.togglePause();
                        break;
                    case '1':
                        if (window.game && window.game.playerShip) {
                            window.game.playerShip.selectWeapon(0);
                        }
                        break;
                    case '2':
                        if (window.game && window.game.playerShip) {
                            window.game.playerShip.selectWeapon(1);
                        }
                        break;
                    case '3':
                        if (window.game && window.game.playerShip) {
                            window.game.playerShip.selectWeapon(2);
                        }
                        break;
                }
            } else if (this.gameState === 'paused' && e.key === 'Escape') {
                this.resumeGame();
            }
        });
    }

    hideAllUI() {
        document.getElementById('start-menu').style.display = 'none';
        document.getElementById('stats').style.display = 'none';
        document.getElementById('health-bar').style.display = 'none';
        document.getElementById('xp-bar').style.display = 'none';
        document.getElementById('weapon-hud').style.display = 'none';
        document.getElementById('controls-hint').style.display = 'none';
        document.getElementById('minimap').style.display = 'none';
        document.getElementById('pause-menu').style.display = 'none';
        document.getElementById('game-over').style.display = 'none';
    }

    showStartMenu() {
        this.hideAllUI();
        document.getElementById('start-menu').style.display = 'block';
        this.gameState = 'menu';
        
        // Auto-select first ship
        if (!this.selectedShip) {
            document.querySelector('.ship-card').click();
        }
    }

    startGame(mode) {
        if (!this.selectedShip) {
            document.querySelector('.ship-card').click();
        }

        this.gameMode = mode;
        this.score = 0;
        this.crates = 0;
        this.level = 1;
        
        this.hideAllUI();
        document.getElementById('stats').style.display = 'block';
        document.getElementById('health-bar').style.display = 'block';
        document.getElementById('xp-bar').style.display = 'block';
        document.getElementById('weapon-hud').style.display = 'block';
        document.getElementById('controls-hint').style.display = 'block';
        document.getElementById('minimap').style.display = 'block';
        
        this.updateUI();
        this.gameState = 'playing';

        // Initialize game if it exists
        if (window.game) {
            window.game.startGame(this.selectedShip, mode);
        }
    }

    togglePause() {
        if (this.gameState === 'playing') {
            this.pauseGame();
        } else if (this.gameState === 'paused') {
            this.resumeGame();
        }
    }

    pauseGame() {
        if (this.gameState !== 'playing') return;
        
        this.gameState = 'paused';
        document.getElementById('pause-menu').style.display = 'block';
        
        if (window.game) {
            window.game.isPaused = true;
        }
    }

    resumeGame() {
        if (this.gameState !== 'paused') return;
        
        this.gameState = 'playing';
        document.getElementById('pause-menu').style.display = 'none';
        
        if (window.game) {
            window.game.isPaused = false;
        }
    }

    showGameOver(finalScore) {
        this.gameState = 'gameover';
        document.getElementById('pause-menu').style.display = 'none';
        document.getElementById('game-over').style.display = 'block';
        document.getElementById('final-score').textContent = `Final Score: ${finalScore}`;
    }

    updateUI() {
        // Update stats
        document.getElementById('score').textContent = this.score;
        document.getElementById('crates').textContent = this.crates;
        document.getElementById('level').textContent = this.level;
        
        const modeDisplay = {
            'freeRoam': 'Free Roam',
            'survival': 'Survival',
            'mission': 'Mission'
        };
        document.getElementById('mode-display').textContent = modeDisplay[this.gameMode] || 'Unknown';
    }

    updateHealth(health, maxHealth) {
        const healthPercent = (health / maxHealth) * 100;
        document.getElementById('health-fill').style.width = healthPercent + '%';
        document.getElementById('health-text').textContent = `${Math.ceil(health)} HP`;
    }

    updateWeaponUI(weaponSystem) {
        weaponSystem.updateUI();
    }

    updateXP(xpProgress) {
        // Update level display in stats
        document.getElementById('level').textContent = xpProgress.level;
        
        // Update XP bar
        const xpPercent = xpProgress.progress * 100;
        document.getElementById('xp-fill').style.width = xpPercent + '%';
        document.getElementById('xp-text').textContent = `${xpProgress.current}/${xpProgress.required} XP`;
    }

    updateMinimap(playerShip, targets, crates, worldSize) {
        const minimapCanvas = document.getElementById('minimap');
        const ctx = minimapCanvas.getContext('2d');
        
        // Clear minimap
        ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        ctx.fillRect(0, 0, 200, 200);
        
        // Calculate scale
        const scale = 200 / (worldSize * 2);
        
        // Draw grid
        ctx.strokeStyle = 'rgba(74, 144, 226, 0.2)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const pos = i * 50;
            ctx.beginPath();
            ctx.moveTo(pos, 0);
            ctx.lineTo(pos, 200);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(0, pos);
            ctx.lineTo(200, pos);
            ctx.stroke();
        }
        
        // Draw crates
        ctx.fillStyle = '#f39c12';
        crates.forEach(crate => {
            const x = (crate.x + worldSize) * scale;
            const y = (crate.y + worldSize) * scale;
            ctx.fillRect(x - 1, y - 1, 2, 2);
        });
        
        // Draw targets
        ctx.fillStyle = '#e74c3c';
        targets.forEach(target => {
            if (!target.isDead) {
                const x = (target.x + worldSize) * scale;
                const y = (target.y + worldSize) * scale;
                ctx.fillRect(x - 2, y - 2, 4, 4);
            }
        });
        
        // Draw player
        ctx.fillStyle = '#2ecc71';
        const playerX = (playerShip.x + worldSize) * scale;
        const playerY = (playerShip.y + worldSize) * scale;
        ctx.fillRect(playerX - 3, playerY - 3, 6, 6);
        
        // Draw player direction
        ctx.strokeStyle = '#2ecc71';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(playerX, playerY);
        ctx.lineTo(
            playerX + Math.cos(playerShip.angle) * 10,
            playerY + Math.sin(playerShip.angle) * 10
        );
        ctx.stroke();
        
        // Draw viewport border
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.lineWidth = 1;
        const viewWidth = (ctx.canvas.width / 2) * scale;
        const viewHeight = (ctx.canvas.height / 2) * scale;
        ctx.strokeRect(
            playerX - viewWidth,
            playerY - viewHeight,
            viewWidth * 2,
            viewHeight * 2
        );
    }

    addScore(points) {
        this.score += points;
        this.checkLevelUp();
        this.updateUI();
    }

    addCrate() {
        this.crates += 1;
        this.addScore(100);
        this.updateUI();
    }

    checkLevelUp() {
        const newLevel = Math.floor(this.score / 1000) + 1;
        if (newLevel > this.level) {
            this.level = newLevel;
            
            // Level up bonus
            if (window.game && window.game.playerShip) {
                window.game.playerShip.heal(25);
                this.showNotification(`LEVEL UP! Level ${this.level}`);
            }
        }
    }

    showNotification(message) {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            color: #f39c12;
            padding: 20px 40px;
            border-radius: 10px;
            border: 2px solid #f39c12;
            font-size: 24px;
            font-weight: bold;
            z-index: 1000;
            pointer-events: none;
            animation: notificationFade 2s ease-out forwards;
        `;
        notification.textContent = message;
        
        // Add CSS animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes notificationFade {
                0% { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
                20% { opacity: 1; transform: translate(-50%, -50%) scale(1.1); }
                80% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
                100% { opacity: 0; transform: translate(-50%, -50%) scale(0.9); }
            }
        `;
        document.head.appendChild(style);
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
            style.remove();
        }, 2000);
    }

    getSelectedShip() {
        return this.selectedShip;
    }

    getGameState() {
        return this.gameState;
    }
}

// Global UI manager instance
const uiManager = new UIManager();

// Global functions for button onclick handlers
function startGame(mode) {
    uiManager.startGame(mode);
}

function resumeGame() {
    uiManager.resumeGame();
}