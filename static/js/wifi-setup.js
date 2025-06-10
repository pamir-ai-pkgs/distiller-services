class WiFiSetup {
    constructor() {
        this.statusCard = document.getElementById('status-card');
        this.statusInfo = document.getElementById('status-info');
        this.ssidInput = document.getElementById('ssid-input');
        this.passwordInput = document.getElementById('password-input');
        this.connectBtn = document.getElementById('connect-btn');
        this.completeBtn = document.getElementById('complete-btn');
        this.alertContainer = document.getElementById('alert-container');
        
        this.init();
    }
    
    init() {
        this.connectBtn.addEventListener('click', () => this.connectToNetwork());
        this.completeBtn.addEventListener('click', () => this.completeSetup());
        
        this.checkStatus();
        setInterval(() => this.checkStatus(), 5000);
    }
    
    async checkStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();
            this.updateStatusDisplay(status);
        } catch (error) {
            console.error('Status check failed:', error);
        }
    }
    
    updateStatusDisplay(status) {
        if (status.connected) {
            this.statusCard.className = 'status-card';
            this.statusInfo.innerHTML = `
                <strong>Connected to:</strong> ${status.ssid}<br>
                <strong>IP Address:</strong> ${status.ip_address || 'N/A'}<br>
                <strong>Interface:</strong> ${status.interface || 'N/A'}
            `;
            this.completeBtn.style.display = 'inline-block';
        } else {
            this.statusCard.className = 'status-card disconnected';
            this.statusInfo.textContent = 'Not connected to any network';
            this.completeBtn.style.display = 'none';
        }
    }
    
    async connectToNetwork() {
        const ssid = this.ssidInput.value.trim();
        const password = this.passwordInput.value;
        
        if (!ssid) {
            this.showAlert('Please enter a network name', 'error');
            return;
        }
        
        this.connectBtn.textContent = 'Connecting...';
        this.connectBtn.disabled = true;
        
        const passwordInfo = password ? 'with password' : '(open network)';
        this.showAlert(`Connecting to ${ssid} ${passwordInfo}... (Hotspot may temporarily disconnect)`, 'info');
        
        try {
            const response = await fetch('/api/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ssid: ssid, password: password })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showAlert(`Successfully connected to ${ssid}`, 'success');
                if (result.hotspot_stopped) {
                    this.showAlert('Setup hotspot has been stopped - you are now connected to your WiFi network', 'info');
                }
                this.checkStatus();
            } else {
                let message = result.message || 'Connection failed';
                if (result.hotspot_restored) {
                    message += ' Setup hotspot has been restored.';
                }
                this.showAlert(message, 'error');
            }
        } catch (error) {
            let errorMessage = 'Connection failed. Please try again.';
            if (error.message) {
                errorMessage = error.message;
            }
            this.showAlert(errorMessage, 'error');
            console.error('Connection error:', error);
        } finally {
            this.connectBtn.textContent = 'Connect';
            this.connectBtn.disabled = false;
        }
    }
    
    async completeSetup() {
        try {
            const response = await fetch('/api/complete-setup', {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                this.showAlert('Setup completed successfully!', 'success');
            }
        } catch (error) {
            console.error('Complete setup failed:', error);
        }
    }
    
    showAlert(message, type) {
        const alertClass = `alert-${type}`;
        const alertHtml = `
            <div class="alert ${alertClass}">
                ${message}
            </div>
        `;
        
        this.alertContainer.innerHTML = alertHtml;
        
        setTimeout(() => {
            this.alertContainer.innerHTML = '';
        }, 5000);
    }
}

// Initialize the WiFi setup interface when the page loads
document.addEventListener('DOMContentLoaded', function() {
    window.wifiSetup = new WiFiSetup();
}); 