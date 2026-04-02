import socket
import threading
import sys
import os

# Add parent directory to path so we can import config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

from security_manager import is_sender_allowed
from crypto import encrypt_payload, decrypt_payload

def handle_client(client_socket, client_addr):
    """Handles an individual connection from Prashant's GUI."""
    print(f"\n[+] Incoming connection from Client: {client_addr}")
    
    try:
        # Read the first packet to determine routing and check security
        initial_data = client_socket.recv(4096)
        if not initial_data:
            client_socket.close()
            return
            
        decoded_data = initial_data.decode('utf-8', errors='ignore')
        print(f"[PROXY INTERCEPT] Initial Payload:\n{decoded_data.strip()}")

        # ---------------------------------------------------------
        # 1. SECURITY CHECK (Blacklist Enforcement)
        # ---------------------------------------------------------
        if "MAIL FROM:" in decoded_data.upper():
            # Extract the email address from the command
            parts = decoded_data.upper().split("MAIL FROM:")
            if len(parts) > 1:
                sender = parts[1].split()[0] # Grab the email part
                if not is_sender_allowed(sender):
                    # Actively reject the connection!
                    client_socket.send(b"550 Requested action not taken: mailbox unavailable (Blacklisted)\r\n")
                    client_socket.close()
                    return

        # ---------------------------------------------------------
        # 2. ROUTING & ENCRYPTION ENGINE
        # ---------------------------------------------------------
        # If the packet looks like SMTP (Sending mail)
        if "EHLO" in decoded_data.upper() or "HELO" in decoded_data.upper() or "SMTP" in decoded_data.upper():
            print(f"[*] Routing {client_addr} to Gaurav (SMTP MTA)")
            
            # Encrypt the payload before sending to Gaurav
            # (In a real system we'd parse the DATA block, but for the project we encrypt the whole message body if we detect it)
            if "DATA_BODY:" in decoded_data:
                # Assuming Prashant formats his final message with a specific tag for easy parsing
                parts = decoded_data.split("DATA_BODY:")
                header = parts[0]
                body = parts[1]
                encrypted_body = encrypt_payload(body)
                modified_data = (header + "DATA_BODY:" + encrypted_body).encode('utf-8')
            else:
                modified_data = initial_data

            forward_traffic(client_socket, modified_data, config.SMTP_IP, config.SMTP_PORT)

        # If the packet looks like POP3 (Fetching mail)
        elif "USER" in decoded_data.upper() or "POP3" in decoded_data.upper():
            print(f"[*] Routing {client_addr} to Sunny (POP3 MAA)")
            # We don't encrypt on the way TO Sunny, we decrypt on the way BACK.
            forward_traffic(client_socket, initial_data, config.POP3_IP, config.POP3_PORT, decrypt_return=True)
            
        else:
            print(f"[!] Unknown protocol signature from {client_addr}. Dropping.")
            client_socket.send(b"ERROR: Unknown Protocol Signature\r\n")
            client_socket.close()

    except Exception as e:
        print(f"[!] Proxy Error handling client: {e}")
        client_socket.close()


def forward_traffic(client_socket, initial_data, target_ip, target_port, decrypt_return=False):
    """Acts as a middleman, passing data between Client and Server."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.connect((target_ip, target_port))
        
        # Send the initial data we intercepted
        server_socket.send(initial_data)
        
        # Set up a continuous bidirectional bridge
        # Thread 1: Client -> Proxy -> Server
        c2s = threading.Thread(target=bridge, args=(client_socket, server_socket, False))
        # Thread 2: Server -> Proxy -> Client
        s2c = threading.Thread(target=bridge, args=(server_socket, client_socket, decrypt_return))
        
        c2s.start()
        s2c.start()
        
    except ConnectionRefusedError:
        print(f"[!] Cannot reach target Server at {target_ip}:{target_port}. Is it running?")
        client_socket.send(b"503 Service Unavailable\r\n")
        client_socket.close()

def bridge(source, destination, apply_decryption):
    """Continuously reads from source and sends to destination."""
    try:
        while True:
            data = source.recv(4096)
            if not data:
                break
                
            if apply_decryption:
                decoded = data.decode('utf-8', errors='ignore')
                if "DATA_BODY:" in decoded:
                    # If fetching from Sunny, decrypt it before giving it to Prashant
                    parts = decoded.split("DATA_BODY:")
                    header = parts[0]
                    encrypted_body = parts[1]
                    decrypted_body = decrypt_payload(encrypted_body)
                    data = (header + "DATA_BODY:" + decrypted_body).encode('utf-8')

            destination.send(data)
    except Exception:
        pass # Expected when sockets close naturally
    finally:
        source.close()
        destination.close()


def start_proxy():
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow port reuse so you don't get "Address already in use" errors while testing
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        proxy.bind((config.PROXY_IP, config.PROXY_PORT))
        proxy.listen(10)
        print("="*50)
        print(f"[*] Ronak's Reverse Proxy & Security Node Active")
        print(f"[*] Listening on {config.PROXY_IP}:{config.PROXY_PORT}")
        print("="*50)

        while True:
            client_socket, addr = proxy.accept()
            # Handle each client in a new thread so multiple clients can connect at once
            client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
            client_thread.start()
            
    except Exception as e:
        print(f"[!] Critical Proxy Error: {e}")
    finally:
        proxy.close()

if __name__ == "__main__":
    start_proxy()