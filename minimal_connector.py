import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import subprocess
import requests
import json
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify
from cryptography.fernet import Fernet
import base64
import hashlib

# Flask app for receiving XML
flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'your-secret-key-here'

# Global variables
AUTH_TOKEN = None
TUNNEL_URL = None
TUNNEL_PROCESS = None
CONFIG_FILE = "connector_config.enc"
KEY_FILE = "connector.key"

class ConnectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TallySync Connector")
        self.root.geometry("700x600")
        self.root.resizable(False, False)
        
        # Check if cloudflared is installed
        if not self.check_cloudflared():
            self.show_download_cloudflared_screen()
        elif self.load_saved_token():
            self.show_main_screen()
        else:
            self.show_login_screen()
    
    def check_cloudflared(self):
        """Check if cloudflared is installed"""
        try:
            result = subprocess.run(['cloudflared', '--version'], 
                                  capture_output=True, 
                                  text=True,
                                  timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def show_download_cloudflared_screen(self):
        """Show screen to download cloudflared"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        frame = tk.Frame(self.root, bg='#f0f0f0')
        frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        title = tk.Label(frame, text="⚙️ Setup Required", 
                        font=('Arial', 18, 'bold'), bg='#f0f0f0')
        title.pack(pady=(0, 20))
        
        msg = tk.Label(frame, 
                      text="Cloudflare Tunnel is required to run the connector.\n\n"
                           "Click below to download and install it automatically.",
                      font=('Arial', 11), bg='#f0f0f0', justify=tk.CENTER)
        msg.pack(pady=20)
        
        self.download_btn = tk.Button(frame, text="Download & Install Cloudflared",
                                     command=self.download_cloudflared,
                                     font=('Arial', 11, 'bold'),
                                     bg='#667eea', fg='white',
                                     padx=20, pady=10,
                                     cursor='hand2')
        self.download_btn.pack(pady=10)
        
        self.status_label = tk.Label(frame, text="", 
                                    font=('Arial', 10), bg='#f0f0f0')
        self.status_label.pack(pady=10)
        
        manual_label = tk.Label(frame, 
                               text="Or download manually from:\n"
                                    "https://github.com/cloudflare/cloudflared/releases",
                               font=('Arial', 9), bg='#f0f0f0', fg='#666')
        manual_label.pack(pady=20)
    
    def download_cloudflared(self):
        """Download and install cloudflared"""
        self.download_btn.config(state='disabled')
        self.status_label.config(text="⏳ Downloading cloudflared...")
        
        def download_thread():
            try:
                # Determine OS and architecture
                system = sys.platform
                
                if system == 'win32':
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
                    filename = "cloudflared.exe"
                elif system == 'darwin':
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
                    filename = "cloudflared"
                else:  # Linux
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                    filename = "cloudflared"
                
                self.status_label.config(text=f"⏳ Downloading from GitHub...")
                
                # Download file
                response = requests.get(url, stream=True, timeout=60)
                response.raise_for_status()
                
                # Save to current directory
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Make executable (Unix-like systems)
                if system != 'win32':
                    os.chmod(filename, 0o755)
                
                self.status_label.config(text="✅ Downloaded successfully!")
                messagebox.showinfo("Success", 
                                  f"Cloudflared downloaded successfully!\n\n"
                                  f"Location: {os.path.abspath(filename)}\n\n"
                                  f"Restarting connector...")
                
                # Restart the app
                if self.load_saved_token():
                    self.show_main_screen()
                else:
                    self.show_login_screen()
                
            except Exception as e:
                self.status_label.config(text=f"❌ Error: {str(e)}")
                self.download_btn.config(state='normal')
                messagebox.showerror("Error", 
                                   f"Failed to download cloudflared:\n{str(e)}\n\n"
                                   f"Please download manually from:\n"
                                   f"https://github.com/cloudflare/cloudflared/releases")
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def get_encryption_key(self):
        """Get or create encryption key"""
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(KEY_FILE, 'wb') as f:
                f.write(key)
            return key
    
    def save_token(self, token):
        """Save token encrypted"""
        try:
            key = self.get_encryption_key()
            fernet = Fernet(key)
            encrypted = fernet.encrypt(token.encode())
            
            with open(CONFIG_FILE, 'wb') as f:
                f.write(encrypted)
            return True
        except Exception as e:
            print(f"Error saving token: {e}")
            return False
    
    def load_saved_token(self):
        """Load saved token if exists"""
        global AUTH_TOKEN
        
        if not os.path.exists(CONFIG_FILE) or not os.path.exists(KEY_FILE):
            return False
        
        try:
            key = self.get_encryption_key()
            fernet = Fernet(key)
            
            with open(CONFIG_FILE, 'rb') as f:
                encrypted = f.read()
            
            token = fernet.decrypt(encrypted).decode()
            AUTH_TOKEN = token
            return True
        except Exception as e:
            print(f"Error loading token: {e}")
            return False
    
    def show_login_screen(self):
        """Show login/setup screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        frame = tk.Frame(self.root, bg='#f0f0f0')
        frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        title = tk.Label(frame, text="TallySync Connector", 
                        font=('Arial', 20, 'bold'), bg='#f0f0f0')
        title.pack(pady=(0, 10))
        
        subtitle = tk.Label(frame, text="Setup Authentication", 
                           font=('Arial', 12), bg='#f0f0f0', fg='#666')
        subtitle.pack(pady=(0, 30))
        
        token_label = tk.Label(frame, text="Enter Auth Token:", 
                              font=('Arial', 11), bg='#f0f0f0')
        token_label.pack(pady=(0, 5))
        
        self.token_entry = tk.Entry(frame, font=('Arial', 11), width=40, show='*')
        self.token_entry.pack(pady=(0, 20))
        self.token_entry.focus()
        
        start_btn = tk.Button(frame, text="Start Connector",
                             command=self.start_connector,
                             font=('Arial', 12, 'bold'),
                             bg='#667eea', fg='white',
                             padx=30, pady=10,
                             cursor='hand2')
        start_btn.pack(pady=10)
        
        self.status_label = tk.Label(frame, text="", 
                                    font=('Arial', 10), bg='#f0f0f0')
        self.status_label.pack(pady=10)
        
        # Bind Enter key
        self.token_entry.bind('<Return>', lambda e: self.start_connector())
    
    def start_connector(self):
        """Start the connector with provided token"""
        global AUTH_TOKEN
        
        token = self.token_entry.get().strip()
        
        if not token:
            messagebox.showerror("Error", "Please enter auth token")
            return
        
        AUTH_TOKEN = token
        
        # Save token
        if self.save_token(token):
            self.status_label.config(text="✅ Token saved")
        
        # Show main screen
        self.show_main_screen()
    
    def show_main_screen(self):
        """Show main connector screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Header
        header = tk.Frame(self.root, bg='#667eea', height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title = tk.Label(header, text="TallySync Connector", 
                        font=('Arial', 16, 'bold'), bg='#667eea', fg='white')
        title.pack(pady=10)
        
        self.status_label = tk.Label(header, text="⚙️ Starting...", 
                                    font=('Arial', 10), bg='#667eea', fg='white')
        self.status_label.pack()
        
        # Main content
        content = tk.Frame(self.root, bg='white')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Tunnel info section
        info_frame = tk.Frame(content, bg='#f8f9fa', relief=tk.RAISED, bd=1)
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(info_frame, text="Tunnel URL:", 
                font=('Arial', 10, 'bold'), bg='#f8f9fa').pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        url_frame = tk.Frame(info_frame, bg='#f8f9fa')
        url_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.tunnel_url_var = tk.StringVar(value="Initializing...")
        self.tunnel_label = tk.Entry(url_frame, textvariable=self.tunnel_url_var,
                                     font=('Courier', 9), state='readonly',
                                     relief=tk.FLAT, bg='white')
        self.tunnel_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        copy_btn = tk.Button(url_frame, text="📋 Copy",
                           command=self.copy_tunnel_url,
                           font=('Arial', 9),
                           cursor='hand2')
        copy_btn.pack(side=tk.LEFT)
        
        # Token info
        token_display = AUTH_TOKEN[:8] + "..." + AUTH_TOKEN[-4:] if len(AUTH_TOKEN) > 12 else AUTH_TOKEN
        tk.Label(info_frame, text=f"Token: {token_display}", 
                font=('Arial', 9), bg='#f8f9fa', fg='#666').pack(anchor=tk.W, padx=10, pady=(0, 10))
        
        # XML display section
        tk.Label(content, text="Received XML:", 
                font=('Arial', 11, 'bold'), bg='white').pack(anchor=tk.W, pady=(0, 5))
        
        self.xml_display = scrolledtext.ScrolledText(content, 
                                                     font=('Courier', 9),
                                                     wrap=tk.WORD,
                                                     bg='#2d3748',
                                                     fg='#e2e8f0',
                                                     insertbackground='white',
                                                     height=20)
        self.xml_display.pack(fill=tk.BOTH, expand=True)
        self.xml_display.insert(1.0, "Waiting for XML data...\n\n"
                                     "The connector is listening for incoming XML from the Render website.")
        self.xml_display.config(state='disabled')
        
        # Buttons
        btn_frame = tk.Frame(content, bg='white')
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        clear_btn = tk.Button(btn_frame, text="Clear Display",
                             command=self.clear_display,
                             font=('Arial', 10),
                             cursor='hand2')
        clear_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        copy_xml_btn = tk.Button(btn_frame, text="Copy XML",
                                command=self.copy_xml,
                                font=('Arial', 10),
                                cursor='hand2')
        copy_xml_btn.pack(side=tk.LEFT, padx=5)
        
        disconnect_btn = tk.Button(btn_frame, text="Disconnect",
                                   command=self.disconnect,
                                   font=('Arial', 10),
                                   bg='#dc3545', fg='white',
                                   cursor='hand2')
        disconnect_btn.pack(side=tk.RIGHT)
        
        # Start tunnel and Flask in background
        threading.Thread(target=self.start_tunnel, daemon=True).start()
        threading.Thread(target=self.start_flask, daemon=True).start()
    
    def start_tunnel(self):
        """Start Cloudflare Tunnel"""
        global TUNNEL_URL, TUNNEL_PROCESS
        
        try:
            self.update_status("⚙️ Starting Cloudflare Tunnel...")
            
            # Find cloudflared in various locations
            cloudflared_path = 'cloudflared'  # Default: try PATH first
            
            # Check common installation locations
            possible_paths = [
                '/opt/homebrew/bin/cloudflared',  # Homebrew Apple Silicon
                '/usr/local/bin/cloudflared',      # Homebrew Intel
                './cloudflared',                    # Current directory
                'cloudflared.exe',                  # Windows current directory
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    cloudflared_path = os.path.abspath(path)
                    break
            
            # Start cloudflared
            cmd = [cloudflared_path, 'tunnel', '--url', 'http://localhost:5001', '--no-autoupdate']
            
            TUNNEL_PROCESS = subprocess.Popen(cmd,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT,
                                             text=True,
                                             bufsize=1)
            
            # Read output to get tunnel URL
            for line in TUNNEL_PROCESS.stdout:
                print(f"DEBUG: {line.strip()}")  # Print every line for debugging
                
                # Look for lines with the actual tunnel URL (has subdomain before trycloudflare.com)
                # Format: https://something-random.trycloudflare.com or https://|  https://something.trycloudflare.com
                if 'trycloudflare.com' in line and ('https://' in line or 'http://' in line):
                    # Make sure it's not just the base domain
                    if line.count('.trycloudflare.com') > 0 or line.count('-') > 0:
                        
                        # Extract URL - look for https://
                        if 'https://' in line:
                            start = line.find('https://')
                            # Find the end of URL (space, pipe, or end of line)
                            rest_of_line = line[start:]
                            end_markers = [' ', '|', '\n', '\r', '\t']
                            end = len(rest_of_line)
                            for marker in end_markers:
                                pos = rest_of_line.find(marker)
                                if pos != -1 and pos < end:
                                    end = pos
                            
                            TUNNEL_URL = rest_of_line[:end].strip()
                        elif 'http://' in line:
                            start = line.find('http://')
                            rest_of_line = line[start:]
                            end_markers = [' ', '|', '\n', '\r', '\t']
                            end = len(rest_of_line)
                            for marker in end_markers:
                                pos = rest_of_line.find(marker)
                                if pos != -1 and pos < end:
                                    end = pos
                            
                            TUNNEL_URL = rest_of_line[:end].strip()
                            # Convert to https
                            TUNNEL_URL = TUNNEL_URL.replace('http://', 'https://')
                        
                        # Clean up URL
                        TUNNEL_URL = TUNNEL_URL.rstrip('.,;:|')
                        
                        # Validate it's a proper tunnel URL (should be longer than just the domain)
                        if len(TUNNEL_URL) > 30:  # Full tunnel URL is longer than base domain
                            # PRINT URL TO TERMINAL
                            print("\n" + "="*70)
                            print("🔗 TUNNEL URL FOUND:")
                            print(TUNNEL_URL)
                            print(f"🔗 Length: {len(TUNNEL_URL)} characters")
                            print("="*70 + "\n")
                            
                            self.tunnel_url_var.set(TUNNEL_URL)
                            self.update_status("🟢 Connected & Listening")
                            break
            
        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to start tunnel:\n{str(e)}")
    
    def start_flask(self):
        """Start Flask server"""
        try:
            flask_app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Flask error: {e}")
    
    def update_status(self, text):
        """Update status label"""
        if hasattr(self, 'status_label'):
            self.status_label.config(text=text)
    
    def copy_tunnel_url(self):
        """Copy tunnel URL to clipboard"""
        if TUNNEL_URL:
            self.root.clipboard_clear()
            self.root.clipboard_append(TUNNEL_URL)
            messagebox.showinfo("Copied", "Tunnel URL copied to clipboard!")
    
    def copy_xml(self):
        """Copy XML to clipboard"""
        xml_content = self.xml_display.get(1.0, tk.END).strip()
        if xml_content and xml_content != "Waiting for XML data...":
            self.root.clipboard_clear()
            self.root.clipboard_append(xml_content)
            messagebox.showinfo("Copied", "XML copied to clipboard!")
    
    def clear_display(self):
        """Clear XML display"""
        self.xml_display.config(state='normal')
        self.xml_display.delete(1.0, tk.END)
        self.xml_display.insert(1.0, "Display cleared. Waiting for new XML...\n")
        self.xml_display.config(state='disabled')
    
    def disconnect(self):
        """Disconnect and return to login"""
        global TUNNEL_PROCESS
        
        if messagebox.askyesno("Confirm", "Disconnect and close tunnel?"):
            if TUNNEL_PROCESS:
                TUNNEL_PROCESS.terminate()
            self.show_login_screen()
    
    def display_xml(self, xml_data):
        """Display received XML"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        self.xml_display.config(state='normal')
        self.xml_display.delete(1.0, tk.END)
        self.xml_display.insert(1.0, f"[{timestamp}] XML Received ✅\n\n{xml_data}")
        self.xml_display.config(state='disabled')

# Create global app instance for Flask to access
app_instance = None

@flask_app.route('/api/receive-xml', methods=['POST'])
def receive_xml():
    """Endpoint to receive XML from Render"""
    global AUTH_TOKEN, app_instance
    
    # Check authorization
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != f'Bearer {AUTH_TOKEN}':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.json
        xml_data = data.get('xml')
        
        if not xml_data:
            return jsonify({'success': False, 'message': 'No XML data provided'}), 400
        
        # Display in Tkinter (run in main thread)
        if app_instance:
            app_instance.root.after(0, lambda: app_instance.display_xml(xml_data))
        
        return jsonify({
            'success': True,
            'message': 'XML received successfully',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@flask_app.route('/api/status', methods=['GET'])
def status():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'tunnel_url': TUNNEL_URL
    })

if __name__ == '__main__':
    root = tk.Tk()
    app_instance = ConnectorApp(root)
    root.mainloop()