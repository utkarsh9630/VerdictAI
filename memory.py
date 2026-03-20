"""Memory system for storing and retrieving past claim verdicts"""
import aiosqlite
import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any
from rapidfuzz import fuzz

class Memory:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialized = False

    async def _ensure_init(self):
        if not self._initialized:
            await self.init_db()
            self._initialized = True
    
    async def init_db(self):
        """Initialize the database schema"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_hash TEXT UNIQUE,
                    claim_text TEXT,
                    normalized_claim TEXT,
                    verdict TEXT,
                    confidence INTEGER,
                    risk_level TEXT,
                    topic TEXT,
                    evidence_for TEXT,
                    evidence_against TEXT,
                    actions_taken TEXT,
                    timestamp TEXT
                )
            """)
            await db.commit()
    
    def normalize_claim(self, claim: str) -> str:
        """Normalize claim text for fuzzy matching"""
        # Lowercase, strip, remove extra spaces
        return " ".join(claim.lower().strip().split())
    
    def hash_claim(self, claim: str) -> str:
        """Generate a hash for the claim"""
        normalized = self.normalize_claim(claim)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    async def find_similar_claim(self, claim: str, threshold: int = 85) -> Optional[Dict[str, Any]]:
        """Find a similar claim using fuzzy matching"""
        await self._ensure_init()
        normalized = self.normalize_claim(claim)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM claims ORDER BY timestamp DESC LIMIT 100"
            )
            rows = await cursor.fetchall()
            
            best_match = None
            best_score = 0
            
            for row in rows:
                score = fuzz.ratio(normalized, row["normalized_claim"])
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = dict(row)
            
            if best_match:
                # Parse JSON fields
                best_match["evidence_for"] = json.loads(best_match["evidence_for"])
                best_match["evidence_against"] = json.loads(best_match["evidence_against"])
                best_match["actions_taken"] = json.loads(best_match["actions_taken"])
                best_match["match_score"] = best_score
            
            return best_match
    
    async def store_claim(self, claim: str, verdict_data: Dict[str, Any]):
        """Store a new claim and its verdict"""
        await self._ensure_init()
        claim_hash = self.hash_claim(claim)
        normalized = self.normalize_claim(claim)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO claims 
                (claim_hash, claim_text, normalized_claim, verdict, confidence, 
                 risk_level, topic, evidence_for, evidence_against, actions_taken, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                claim_hash,
                claim,
                normalized,
                verdict_data.get("verdict"),
                verdict_data.get("confidence"),
                verdict_data.get("risk_level"),
                verdict_data.get("topic"),
                json.dumps(verdict_data.get("evidence_for", [])),
                json.dumps(verdict_data.get("evidence_against", [])),
                json.dumps(verdict_data.get("actions", {})),
                datetime.utcnow().isoformat()
            ))
            await db.commit()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) as count FROM claims")
            row = await cursor.fetchone()
            total_claims = row[0] if row else 0
            
            cursor = await db.execute("""
                SELECT verdict, COUNT(*) as count 
                FROM claims 
                GROUP BY verdict
            """)
            verdict_counts = {row[0]: row[1] for row in await cursor.fetchall()}
            
            return {
                "total_claims": total_claims,
                "verdict_breakdown": verdict_counts
            }
