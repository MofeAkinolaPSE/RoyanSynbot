from src.auth_utils import hash_password

def seed_admin():
    import os
    from dotenv import load_dotenv
    from src.db import db as client
    
    load_dotenv()
    
    email = os.getenv("ADMIN_EMAIL", "admin@royanhospital.com")
    pwd = os.getenv("ADMIN_PASSWORD")
    if not pwd:
        raise RuntimeError("ADMIN_PASSWORD env var must be set before seeding — add it to .env")
    hashed = hash_password(pwd)
    
    print(f"Checking if {email} exists...")
    existing = client.table("royan_users").select("id").eq("email", email).execute()
    
    if existing.data:
        # Update existing admin
        user_id = existing.data[0]["id"]
        print(f"Updating existing admin {user_id}...")
        client.table("royan_users").update({
            "hashed_password": hashed,
            "roles": ["admin"],
            "is_active": True
        }).eq("id", user_id).execute()
        print("Updated.")
    else:
        # Create new admin
        print(f"Creating new admin {email}...")
        client.table("royan_users").insert({
            "email": email,
            "hashed_password": hashed,
            "roles": ["admin"],
            "is_active": True
        }).execute()
        print("Created.")

if __name__ == "__main__":
    seed_admin()
