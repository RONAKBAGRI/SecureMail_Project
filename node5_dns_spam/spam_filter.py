import os

def check_spam(email_body):
    score = 0
    # Find the keywords file in the same directory
    keywords_file = os.path.join(os.path.dirname(__file__), 'spam_keywords.txt')
    
    try:
        with open(keywords_file, 'r') as f:
            # Read words and convert to lowercase
            keywords = [line.strip().lower() for line in f if line.strip()]
    except FileNotFoundError:
        print("[!] Warning: spam_keywords.txt not found. Using defaults.")
        keywords = ["lottery", "urgent", "winner", "password"]

    body_lower = email_body.lower()

    # Rule 1: Check for blacklisted keywords
    for word in keywords:
        if word in body_lower:
            score += 15  # Add 15 points for every bad word found

    # Rule 2: Heuristic - Too many links
    if body_lower.count("http") >= 2:
        score += 20
        
    # Rule 3: Heuristic - SHOUTING
    if email_body.isupper() and len(email_body) > 10:
        score += 30

    # Threshold: If score is 30 or more, it is spam
    is_spam = score >= 30
    return is_spam, score