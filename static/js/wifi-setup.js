class WiFiSetup {
    constructor() {
        this.statusCard = document.getElementById('status-card');
        this.statusInfo = document.getElementById('status-info');
        this.ssidInput = document.getElementById('ssid-input');
        this.passwordInput = document.getElementById('password-input');
        this.connectBtn = document.getElementById('connect-btn');
        // this.completeBtn = document.getElementById('complete-btn'); // Commented out
        this.alertContainer = document.getElementById('alert-container');
        
        this.init();
    }
    
    init() {
        this.connectBtn.addEventListener('click', () => this.connectToNetwork());
        // this.completeBtn.addEventListener('click', () => this.completeSetup()); // Commented out
        
        // Remove automatic status checking since we'll redirect to status page
        // this.checkStatus();
        // setInterval(() => this.checkStatus(), 5000);
        
        // Show initial disconnected state
        this.updateStatusDisplay({ connected: false });
    }
    
    // Keep this method but don't use it automatically
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
            // this.completeBtn.style.display = 'inline-block'; // Commented out
        } else {
            this.statusCard.className = 'status-card disconnected';
            this.statusInfo.textContent = 'Ready to connect to WiFi network';
            // this.completeBtn.style.display = 'none'; // Commented out
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
        this.showAlert(`Connecting to ${ssid} ${passwordInfo}... This may take a moment.`, 'info');
        
        try {
            // Start the connection request
            const response = await fetch('/api/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ssid: ssid, password: password })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Success - redirect to status page
                this.showAlert(`Successfully connected to ${ssid}! Redirecting to status page...`, 'success');
                setTimeout(() => {
                    const currentPort = window.location.port || '8080';
                    const redirectUrl = `http://distiller.local:${currentPort}/wifi_status`;
                    window.location.href = redirectUrl;
                }, 2000);
                
            } else if (result.redirect_to_status) {
                // Network exists but connection will be attempted (hotspot will go down)
                this.showAlert(`Attempting connection... Redirecting to check status.`, 'info');
                setTimeout(() => {
                    const currentPort = window.location.port || '8080';
                    const redirectUrl = `http://distiller.local:${currentPort}/wifi_status`;
                    window.location.href = redirectUrl;
                }, 2000);
                
            } else {
                // Network doesn't exist or other immediate error (no hotspot disruption)
                this.showAlert(result.message || 'Connection failed. Please check your credentials and try again.', 'error');
                this.connectBtn.textContent = 'Connect';
                this.connectBtn.disabled = false;
            }
            
        } catch (error) {
            // Network error - likely means hotspot went down during connection attempt
            this.showAlert('Connection in progress... Redirecting to check status.', 'info');
            
            setTimeout(() => {
                const currentPort = window.location.port || '8080';
                const redirectUrl = `http://distiller.local:${currentPort}/wifi_status`;
                window.location.href = redirectUrl;
            }, 3000);
        }
    }
    
    // Commented out complete setup functionality
    /*
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
    */
    
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