"""Initialize Nexus Games DB: load schema.sql, seed products + admin user."""
import os
import sqlite3
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get('DATABASE_PATH', 'nexus_games.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

PRODUCTS = [
    (1, "God of War Ragnarok", 69.99, "Action-Adventure",
     "Experience the epic conclusion of Kratos's Norse saga. As Fimbulwinter begins, Kratos must face his greatest challenge yet in this cinematic masterpiece featuring stunning visuals and intense combat.",
     "photos/ragnarok.jpg", 100),
    (2, "Assassin's Creed Mirage", 59.99, "Action-Adventure",
     "Return to the Golden Age of Assassins. Become Basim, a cunning street thief in 9th century Baghdad, and master the tools, skills, and knowledge needed to become a legendary assassin.",
     "photos/assain creed.jpg", 100),
    (3, "The Witcher 3: Wild Hunt", 49.99, "RPG",
     "The ultimate story-driven RPG. Hunt monsters, find treasure, and make impactful choices in a vast open world. Discover why this game is considered one of the greatest RPGs ever made.",
     "photos/the witcher.jfif", 100),
    (4, "Cyberpunk 2077", 59.99, "RPG",
     "An open-world action-RPG set in the dystopian Night City. Play as V, a mercenary navigating a dangerous megacity filled with cutting-edge technology, corporate corruption, and unforgettable characters.",
     "photos/cyberpunk.jpg", 100),
    (5, "Elden Ring", 59.99, "Action-RPG",
     "A masterpiece from FromSoftware and George R.R. Martin. Explore a breathtaking open world, master challenging combat, and uncover the secrets of the Lands Between.",
     "photos/download.jfif", 100),
    (6, "Red Dead Redemption 2", 59.99, "Action-Adventure",
     "An immersive Wild West epic. Live as an outlaw in a stunning open world with gripping storytelling, dynamic gameplay, and unforgettable characters. The pinnacle of open-world design.",
     "photos/rdr2.jfif", 100),
    (7, "The Last of Us Part II", 54.99, "Action-Adventure",
     "An emotional and visceral journey in a post-apocalyptic world. Experience a gripping narrative following Ellie as she seeks revenge in a morally complex story that challenges everything you believe.",
     "photos/the last of us 2.jfif", 100),
    (8, "Starfield", 69.99, "RPG",
     "Explore 1000 planets in this sci-fi RPG from Bethesda. Create your character, build your ship, and chart your own path through a vast universe filled with exploration, combat, and endless possibility.",
     "photos/starfield.jfif", 100),
]


def main():
    print(f"[seed] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    print("[seed] Schema loaded.")

    conn.executemany(
        "INSERT INTO products (id, title, price, category, description, image, stock) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        PRODUCTS,
    )
    print(f"[seed] Inserted {len(PRODUCTS)} products.")

    admin_user = os.environ.get('ADMIN_SEED_USERNAME', 'admin')
    admin_email = os.environ.get('ADMIN_SEED_EMAIL', 'admin@nexusgames.local')
    admin_pass = os.environ.get('ADMIN_SEED_PASSWORD', 'Admin1234')
    conn.execute(
        "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, 1)",
        (admin_user, admin_email, generate_password_hash(admin_pass)),
    )
    print(f"[seed] Admin user '{admin_user}' created (password from .env).")

    demo_user = os.environ.get('DEMO_SEED_USERNAME', 'demo')
    demo_email = os.environ.get('DEMO_SEED_EMAIL', 'demo@nexusgames.local')
    demo_pass = os.environ.get('DEMO_SEED_PASSWORD', 'Demo1234')
    conn.execute(
        "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, 0)",
        (demo_user, demo_email, generate_password_hash(demo_pass)),
    )
    print(f"[seed] Demo user '{demo_user}' created.")

    conn.commit()
    conn.close()
    print("[seed] Done.")


if __name__ == '__main__':
    main()
