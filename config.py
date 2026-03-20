"""Configuration management for DebateShield Lite"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    # You.com
    YOU_API_KEY = os.getenv("YOU_API_KEY", "")
    
    # App
    APP_ENV = os.getenv("APP_ENV", "dev")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "/tmp/verdictai.db")
    
    @classmethod
    def validate(cls):
        """Check if required keys are present"""
        missing = []
        if not cls.LLM_API_KEY:
            missing.append("LLM_API_KEY")
        if not cls.YOU_API_KEY:
            missing.append("YOU_API_KEY")
        
        if missing:
            print(f"WARNING: Missing required config keys: {', '.join(missing)}")
            print("   Core features may not work without proper API keys")
        
        return len(missing) == 0

config = Config()