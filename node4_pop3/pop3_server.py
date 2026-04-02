import socket
import threading
import os
import sys

# Ensure Python can find config.py in the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# Paths
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.txt')
STORAGE_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage'))

def load_users():
    """Loads username:password pairs into a dictionary."""
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    u, p = line.strip().split(':', 1)
                    users[u] = p
    return users

def get_user_emails(username):
    """Returns a list of email file paths for the user."""
    inbox_path = os.path.join(STORAGE_BASE, username, 'inbox')
    if not os.path.exists(inbox_path):
        os.makedirs(inbox_path) # Auto-create directory if it doesn't exist
        return []
    
    # Return list of files, sorted by creation time
    files = [os.path.join(inbox_path, f) for f in os.listdir(inbox_path) if os.path.isfile(os.path.join(inbox_path, f))]
    return sorted(files)

def handle_client(client_socket, address):
    print(f"[+] POP3 Connection accepted from {address}")
    client_socket.send(b"+OK POP3 Server Ready\r\n")
    
    users_db = load_users()
    current_user = None
    authenticated = False
    
    while True:
        try:
            data = client_socket.recv(1024).decode().strip()
            if not data:
                break
            
            print(f"[{address}] C: {data}")
            parts = data.split(' ', 1)
            command = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            # --- POP3 STATE MACHINE ---
            if command == "USER":
                current_user = args
                if current_user in users_db:
                    client_socket.send(b"+OK User accepted\r\n")
                else:
                    client_socket.send(b"-ERR Unknown user\r\n")
                    current_user = None
            
            elif command == "PASS":
                if current_user and args == users_db.get(current_user):
                    authenticated = True
                    client_socket.send(b"+OK Pass accepted\r\n")
                else:
                    client_socket.send(b"-ERR Invalid password\r\n")
            
            elif command == "STAT" and authenticated:
                emails = get_user_emails(current_user)
                total_size = sum(os.path.getsize(f) for f in emails)
                client_socket.send(f"+OK {len(emails)} {total_size}\r\n".encode())
                
            elif command == "LIST" and authenticated:
                emails = get_user_emails(current_user)
                total_size = sum(os.path.getsize(f) for f in emails)
                client_socket.send(f"+OK {len(emails)} messages ({total_size} octets)\r\n".encode())
                for i, filepath in enumerate(emails, 1):
                    client_socket.send(f"{i} {os.path.getsize(filepath)}\r\n".encode())
                client_socket.send(b".\r\n")
                
            elif command == "RETR" and authenticated:
                try:
                    msg_idx = int(args) - 1
                    emails = get_user_emails(current_user)
                    if 0 <= msg_idx < len(emails):
                        filepath = emails[msg_idx]
                        client_socket.send(f"+OK {os.path.getsize(filepath)} octets\r\n".encode())
                        with open(filepath, 'r', encoding='utf-8') as f:
                            client_socket.sendall(f.read().encode() + b"\r\n")
                        client_socket.send(b".\r\n")
                        
                        # [Future Feature]: Trigger read-receipt to Gaurav here
                    else:
                        client_socket.send(b"-ERR No such message\r\n")
                except ValueError:
                    client_socket.send(b"-ERR Invalid message number\r\n")
                    
            elif command == "QUIT":
                client_socket.send(b"+OK POP3 Server signing off\r\n")
                break
            else:
                client_socket.send(b"-ERR Command not recognized or not authenticated\r\n")
                
        except Exception as e:
            print(f"[!] Error with {address}: {e}")
            break

    print(f"[-] Connection closed for {address}")
    client_socket.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((config.POP3_IP, config.POP3_PORT))
    server.listen(5)
    print(f"[*] POP3 Server Listening on {config.POP3_IP}:{config.POP3_PORT}")
    
    # Ensure base storage directory exists
    if not os.path.exists(STORAGE_BASE):
        os.makedirs(STORAGE_BASE)

    while True:
        client_sock, addr = server.accept()
        # Handle multiple clients simultaneously
        client_thread = threading.Thread(target=handle_client, args=(client_sock, addr))
        client_thread.start()

if __name__ == "__main__":
    start_server()