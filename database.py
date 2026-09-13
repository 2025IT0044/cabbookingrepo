import sqlite3

DATABASE = "cab_booking.db"


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db_connection():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    return conn


# ==========================================
# CREATE TABLES
# ==========================================

def create_tables():

    conn = get_db_connection()
    cursor = conn.cursor()


    # ======================================
    # USERS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # ======================================
    # ADD DEMO USERS
    # ======================================

    demo_users = [
        ("RideGo User 1", "user1@ridego.com", "9000000001", "User@123"),
        ("RideGo User 2", "user2@ridego.com", "9000000002", "User@456"),
        ("RideGo User 3", "user3@ridego.com", "9000000003", "User@789"),
        ("RideGo User 4", "user4@ridego.com", "9000000004", "User@321")
    ]

    for name, email, phone, password in demo_users:
        cursor.execute("""
            INSERT INTO users (name, email, phone, password)
            SELECT ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM users
                WHERE email = ?
            )
        """, (name, email, phone, password, email))


    # ======================================
    # DRIVERS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            license_no TEXT,
            email TEXT,
            password TEXT,
            status TEXT DEFAULT 'Available'
        )
    """)

    driver_columns = [
        row["name"]
        for row in cursor.execute("PRAGMA table_info(drivers)").fetchall()
    ]

    if "email" not in driver_columns:
        cursor.execute("ALTER TABLE drivers ADD COLUMN email TEXT")

    if "password" not in driver_columns:
        cursor.execute("ALTER TABLE drivers ADD COLUMN password TEXT")


    # ======================================
    # CABS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cabs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER,
            cab_type TEXT NOT NULL,
            car_number TEXT NOT NULL,
            FOREIGN KEY (driver_id) REFERENCES drivers(id)
        )
    """)


    # ======================================
    # BOOKINGS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            driver_id INTEGER,
            pickup TEXT NOT NULL,
            destination TEXT NOT NULL,
            cab_type TEXT NOT NULL,
            fare REAL NOT NULL,
            status TEXT DEFAULT 'Searching',
            booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (driver_id) REFERENCES drivers(id)
        )
    """)


    # ======================================
    # PAYMENTS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            payment_time TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        )
    """)

    payment_columns = [
        row["name"]
        for row in cursor.execute("PRAGMA table_info(payments)").fetchall()
    ]

    if "payment_time" not in payment_columns:

        cursor.execute("""
            ALTER TABLE payments
            ADD COLUMN payment_time TIMESTAMP
        """)


    # ======================================
    # RATINGS TABLE
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            review TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        )
    """)


    # ======================================
    # ADD DEMO DRIVERS
    # ======================================

    driver_count = cursor.execute("""
        SELECT COUNT(*) FROM drivers
    """).fetchone()[0]


    if driver_count == 0:

        # Driver 1
        cursor.execute("""
            INSERT INTO drivers
            (name, phone, license_no, email, password, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Arun Kumar",
            "9876543210",
            "TN01DL1234",
            "arun@ridego.com",
            "driver123",
            "Available"
        ))


        # Driver 2
        cursor.execute("""
            INSERT INTO drivers
            (name, phone, license_no, email, password, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Rahul Kumar",
            "9876543211",
            "TN02DL5678",
            "rahul@ridego.com",
            "driver123",
            "Available"
        ))


        # Driver 3
        cursor.execute("""
            INSERT INTO drivers
            (name, phone, license_no, email, password, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Vijay Kumar",
            "9876543212",
            "TN03DL9012",
            "vijay@ridego.com",
            "driver123",
            "Available"
        ))

    demo_driver_credentials = [
        (1, "arun@ridego.com", "driver123"),
        (2, "rahul@ridego.com", "driver123"),
        (3, "vijay@ridego.com", "driver123")
    ]

    for driver_id, email, password in demo_driver_credentials:
        cursor.execute("""
            UPDATE drivers
            SET email = COALESCE(NULLIF(email, ''), ?),
                password = COALESCE(NULLIF(password, ''), ?)
            WHERE id = ?
        """, (email, password, driver_id))


    # ======================================
    # ADD DEMO CABS
    # ======================================

    cab_count = cursor.execute("""
        SELECT COUNT(*) FROM cabs
    """).fetchone()[0]


    if cab_count == 0:

        # Arun - Auto
        cursor.execute("""
            INSERT INTO cabs
            (driver_id, cab_type, car_number)
            VALUES (?, ?, ?)
        """, (
            1,
            "Auto",
            "TN 01 AB 1234"
        ))


        # Rahul - Mini
        cursor.execute("""
            INSERT INTO cabs
            (driver_id, cab_type, car_number)
            VALUES (?, ?, ?)
        """, (
            2,
            "Mini",
            "TN 02 CD 5678"
        ))


        # Vijay - Sedan
        cursor.execute("""
            INSERT INTO cabs
            (driver_id, cab_type, car_number)
            VALUES (?, ?, ?)
        """, (
            3,
            "Sedan",
            "TN 03 EF 9012"
        ))


    conn.commit()
    conn.close()


# ==========================================
# RUN DATABASE SETUP
# ==========================================

if __name__ == "__main__":

    create_tables()

    print("Database and tables created successfully!")
    print("Demo drivers and cabs added successfully!")