import joblib
import os

class SpamFilterModule:
    """
    Middleware module for scanning inbound emails in the Secure Email network.
    """
    def __init__(self, model_path='spam_logistic_model.pkl', vec_path='tfidf_vectorizer.pkl'):
        # Check if files exist to prevent node crash on startup
        if not os.path.exists(model_path) or not os.path.exists(vec_path):
            raise FileNotFoundError(f"Model artifacts not found. Ensure {model_path} and {vec_path} are in the same directory.")
            
        print("[SpamFilter] Loading AI models into memory...")
        self.model = joblib.load(model_path)
        self.vectorizer = joblib.load(vec_path)
        print("[SpamFilter] Initialized and ready.")

    def is_spam(self, email_body_text: str) -> bool:
        """
        Takes raw email text, applies TF-IDF transformation, 
        and mathematically predicts if it is Spam.
        """
        # Failsafe for empty emails
        if not email_body_text or not str(email_body_text).strip():
            return False 
            
        # 1. Transform text using the exact mathematical vocabulary from training
        features = self.vectorizer.transform([str(email_body_text)])
        
        # 2. Predict using the balanced Logistic Regression model
        prediction = self.model.predict(features)
        
        # 3. Return boolean (1 is mapped to Spam)
        return bool(prediction[0] == 1)