from flask import Flask, jsonify, render_template, request, redirect, session, url_for
from database import create_tables, get_db_connection


app = Flask(__name__)
app.secret_key = "ridego-demo-secret"


def current_tab_id():

    return (
        request.args.get("tab_id")
        or request.form.get("tab_id")
        or request.headers.get("X-RideGo-Tab")
        or "default"
    )


def current_tab_state():

    tab_sessions = session.get("tab_sessions", {})
    return tab_sessions.get(current_tab_id(), {})


def save_tab_state(state):

    tab_sessions = session.get("tab_sessions", {})
    tab_sessions[current_tab_id()] = state
    session["tab_sessions"] = tab_sessions
    session.modified = True


def tab_url(endpoint, **values):

    values["tab_id"] = current_tab_id()
    return url_for(endpoint, **values)


def current_user_id():

    state = current_tab_state()

    if state.get("role") == "user":
        return state.get("user_id")

    if current_tab_id() == "default" and session.get("role") == "user":
        return session.get("user_id")

    return None


def current_driver_id():

    state = current_tab_state()

    if state.get("role") == "driver":
        return state.get("driver_id")

    if current_tab_id() == "default" and session.get("role") == "driver":
        return session.get("driver_id")

    return None


def user_required():

    if current_user_id() is None:
        return redirect(tab_url("login"))

    return None


def driver_required():

    if current_driver_id() is None:
        return redirect(tab_url("login"))

    return None


# ==========================================
# CREATE DATABASE TABLES
# ==========================================

create_tables()


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    return render_template("index.html")


# ==========================================
# ABOUT AND CONTACT
# ==========================================

@app.route("/about")
def about():

    return render_template("about.html")


@app.route("/contact")
def contact():

    return render_template("contact.html")


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        conn = get_db_connection()

        try:

            conn.execute("""
                INSERT INTO users
                (name, email, phone, password)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                phone,
                password
            ))

            conn.commit()

        except Exception as e:

            conn.close()

            return f"Registration failed: {e}"

        conn.close()

        return redirect(tab_url("login"))

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        role = request.form.get("role", "user").lower()
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()

        if role == "driver":
            account = conn.execute("""
                SELECT *
                FROM drivers
                WHERE email = ?
                AND password = ?
            """, (email, password)).fetchone()
        else:
            role = "user"
            account = conn.execute("""
                SELECT *
                FROM users
                WHERE email = ?
                AND password = ?
            """, (email, password)).fetchone()

        conn.close()

        if account:

            state = {
                "role": role,
                "active_booking_id": None,
                "payment_success_booking_id": None
            }

            if role == "driver":
                state["driver_id"] = account["id"]
                save_tab_state(state)
                return redirect(tab_url("driver_dashboard"))

            state["user_id"] = account["id"]
            save_tab_state(state)

            return redirect(tab_url("book_ride"))

        return render_template(
            "login.html",
            error=f"Invalid {role.capitalize()} credentials"
        )

    return render_template("login.html", tab_id=current_tab_id())


@app.route("/logout")
def logout():

    tab_sessions = session.get("tab_sessions", {})
    tab_sessions.pop(current_tab_id(), None)

    if tab_sessions:
        session["tab_sessions"] = tab_sessions
        session.modified = True
    else:
        session.clear()

    return redirect(tab_url("login"))


# ==========================================
# USER DASHBOARD
# ==========================================

@app.route("/dashboard")
def user_dashboard():

    guard = user_required()
    if guard:
        return guard

    return redirect(tab_url("book_ride"))


# ==========================================
# USER RIDE HISTORY
# ==========================================

@app.route("/ride-history")
def ride_history():

    guard = user_required()
    if guard:
        return guard

    user_id = current_user_id()

    conn = get_db_connection()

    rides = conn.execute("""
        SELECT
            bookings.*,
            ratings.id AS rating_id,
            ratings.rating,
            ratings.review,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM payments
                    WHERE payments.booking_id = bookings.id
                    AND payments.status = 'Paid'
                ) THEN 'Paid'
                ELSE 'Unpaid'
            END AS payment_status
        FROM bookings
        LEFT JOIN ratings ON ratings.booking_id = bookings.id
        WHERE bookings.user_id = ?
        ORDER BY bookings.booking_time DESC, bookings.id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "ride_history.html",
        rides=rides
    )


# ==========================================
# USER RATING AND REVIEW
# ==========================================

@app.route("/rate/<int:booking_id>", methods=["POST"])
def rate_ride(booking_id):

    guard = user_required()
    if guard:
        return guard

    user_id = current_user_id()

    conn = get_db_connection()

    # Lock the short validation and insert transaction so a booking cannot
    # receive duplicate reviews from simultaneous submissions.
    conn.execute("BEGIN IMMEDIATE")

    booking = conn.execute("""
        SELECT
            bookings.id,
            bookings.user_id,
            bookings.status,
            EXISTS (
                SELECT 1
                FROM payments
                WHERE payments.booking_id = bookings.id
                AND payments.status = 'Paid'
            ) AS is_paid
        FROM bookings
        WHERE bookings.id = ?
        AND bookings.user_id = ?
    """, (booking_id, user_id)).fetchone()

    rating_value = request.form.get("rating", "").strip()

    try:
        rating = int(rating_value)
    except (TypeError, ValueError):
        conn.rollback()
        conn.close()
        return redirect(tab_url("ride_history"))

    if (
        not booking
        or booking["status"] != "Completed"
        or not booking["is_paid"]
        or rating < 1
        or rating > 5
    ):
        conn.rollback()
        conn.close()
        return redirect(tab_url("ride_history"))

    existing_rating = conn.execute("""
        SELECT id
        FROM ratings
        WHERE booking_id = ?
        LIMIT 1
    """, (booking_id,)).fetchone()

    if existing_rating:
        conn.rollback()
        conn.close()
        return redirect(tab_url("ride_history"))

    review = request.form.get("review", "").strip()

    conn.execute("""
        INSERT INTO ratings (booking_id, rating, review)
        VALUES (?, ?, ?)
    """, (booking_id, rating, review))

    conn.commit()
    conn.close()

    return redirect(tab_url("ride_history"))


# ==========================================
# BOOK A RIDE
# ==========================================

@app.route("/book", methods=["GET", "POST"])
def book_ride():

    guard = user_required()
    if guard:
        return guard

    user_id = current_user_id()
    state = current_tab_state()

    if request.args.get("reset") == "1":
        state.pop("active_booking_id", None)
        state.pop("payment_success_booking_id", None)
        save_tab_state(state)
        return redirect(tab_url("book_ride"))

    if request.method == "POST":

        pickup = request.form["pickup"]
        destination = request.form["destination"]
        cab_type = request.form["cab_type"]


        # --------------------------------------
        # CALCULATE FARE
        # --------------------------------------

        if cab_type == "Auto":

            fare = 100

        elif cab_type == "Mini":

            fare = 150

        else:

            fare = 200


        conn = get_db_connection()


        # --------------------------------------
        # FIND AVAILABLE DRIVER
        # --------------------------------------

        driver = conn.execute("""
            SELECT
                drivers.id,
                drivers.name,
                drivers.phone,
                drivers.license_no,
                cabs.cab_type,
                cabs.car_number
            FROM drivers
            JOIN cabs
            ON drivers.id = cabs.driver_id
            WHERE drivers.status = 'Available'
            AND cabs.cab_type = ?
            LIMIT 1
        """, (cab_type,)).fetchone()


        # --------------------------------------
        # DRIVER FOUND
        # --------------------------------------

        if driver:

            driver_id = driver["id"]

            # IMPORTANT:
            # User should initially see
            # "Finding a driver"
            status = "Searching"


            # ----------------------------------
            # CREATE BOOKING
            # ----------------------------------

            cursor = conn.execute("""
                INSERT INTO bookings
                (
                    user_id,
                    driver_id,
                    pickup,
                    destination,
                    cab_type,
                    fare,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                driver_id,
                pickup,
                destination,
                cab_type,
                fare,
                status
            ))


            booking_id = cursor.lastrowid


            # ----------------------------------
            # MAKE DRIVER BUSY
            # ----------------------------------

            conn.execute("""
                UPDATE drivers
                SET status = 'Busy'
                WHERE id = ?
            """, (driver_id,))


            conn.commit()

            conn.close()

            state["active_booking_id"] = booking_id
            state.pop("payment_success_booking_id", None)
            save_tab_state(state)
            return redirect(tab_url("book_ride"))


        # --------------------------------------
        # NO DRIVER AVAILABLE
        # --------------------------------------

        else:

            status = "Searching"


            cursor = conn.execute("""
                INSERT INTO bookings
                (
                    user_id,
                    pickup,
                    destination,
                    cab_type,
                    fare,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                pickup,
                destination,
                cab_type,
                fare,
                status
            ))


            booking_id = cursor.lastrowid


            conn.commit()

            conn.close()

            state["active_booking_id"] = booking_id
            state.pop("payment_success_booking_id", None)
            save_tab_state(state)
            return redirect(tab_url("book_ride"))


    active_booking = None

    active_booking_id = state.get("active_booking_id")

    if active_booking_id:

        conn = get_db_connection()

        active_booking = conn.execute("""
            SELECT
                bookings.*,
                drivers.name AS driver_name,
                drivers.phone,
                cabs.car_number,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM payments
                        WHERE payments.booking_id = bookings.id
                        AND payments.status = 'Paid'
                    ) THEN 'Paid'
                    ELSE 'Unpaid'
                END AS payment_status,
                ratings.id AS rating_id,
                ratings.rating,
                ratings.review
            FROM bookings
            LEFT JOIN drivers ON drivers.id = bookings.driver_id
            LEFT JOIN cabs ON cabs.driver_id = bookings.driver_id
            LEFT JOIN ratings ON ratings.booking_id = bookings.id
            WHERE bookings.id = ?
            AND bookings.user_id = ?
            LIMIT 1
        """, (active_booking_id, user_id)).fetchone()

        conn.close()

        if not active_booking:
            state.pop("active_booking_id", None)
            save_tab_state(state)

        elif active_booking["status"] == "Cancelled":
            state.pop("active_booking_id", None)
            state.pop("payment_success_booking_id", None)
            save_tab_state(state)
            active_booking = None

    return render_template(
        "book_ride.html",
        active_booking=active_booking,
        payment_success=(state.get("payment_success_booking_id") == active_booking_id)
    )


@app.route("/book/status/<int:booking_id>")
def book_status(booking_id):

    if current_user_id() is None or current_tab_state().get("active_booking_id") != booking_id:
        return jsonify({"error": "Booking not found"}), 404

    conn = get_db_connection()

    booking = conn.execute("""
        SELECT
            bookings.status,
            drivers.name AS driver_name,
            drivers.phone AS driver_phone,
            cabs.car_number,
            bookings.cab_type,
            bookings.pickup,
            bookings.destination,
            bookings.fare,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM payments
                    WHERE payments.booking_id = bookings.id
                    AND payments.status = 'Paid'
                ) THEN 'Paid'
                ELSE 'Unpaid'
            END AS payment_status
        FROM bookings
        LEFT JOIN drivers ON drivers.id = bookings.driver_id
        LEFT JOIN cabs ON cabs.driver_id = bookings.driver_id
        WHERE bookings.id = ?
        AND bookings.user_id = ?
    """, (booking_id, current_user_id())).fetchone()

    conn.close()

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    return jsonify({
        "status": booking["status"],
        "driver_name": booking["driver_name"],
        "driver_phone": booking["driver_phone"],
        "car_number": booking["car_number"],
        "cab_type": booking["cab_type"],
        "pickup": booking["pickup"],
        "destination": booking["destination"],
        "fare": booking["fare"],
        "payment_status": booking["payment_status"]
    })


@app.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel_ride(booking_id):

    guard = user_required()
    if guard:
        return guard

    user_id = current_user_id()

    state = current_tab_state()

    if state.get("active_booking_id") != booking_id:
        return redirect(tab_url("book_ride"))

    conn = get_db_connection()

    booking = conn.execute("""
        SELECT id, driver_id, status
        FROM bookings
        WHERE id = ?
        AND user_id = ?
    """, (booking_id, user_id)).fetchone()

    if booking and booking["status"] in ("Searching", "Accepted"):

        conn.execute("""
            UPDATE bookings
            SET status = 'Cancelled'
            WHERE id = ?
            AND user_id = ?
            AND status IN ('Searching', 'Accepted')
        """, (booking_id, user_id))

        if booking["driver_id"]:
            conn.execute("""
                UPDATE drivers
                SET status = 'Available'
                WHERE id = ?
            """, (booking["driver_id"],))

        conn.commit()

    conn.close()
    state.pop("active_booking_id", None)
    state.pop("payment_success_booking_id", None)
    save_tab_state(state)

    return redirect(tab_url("book_ride"))


# ==========================================
# DRIVER DASHBOARD
# ==========================================

@app.route("/driver/dashboard")
def driver_dashboard():

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()

    today_rides = conn.execute("""
        SELECT COUNT(*) AS ride_count
        FROM bookings
        WHERE driver_id = ?
        AND status = 'Completed'
        AND date(booking_time) = date('now')
        AND EXISTS (
            SELECT 1
            FROM payments
            WHERE payments.booking_id = bookings.id
            AND payments.status = 'Paid'
            AND date(payments.payment_time) = date('now')
        )
    """, (driver_id,)).fetchone()["ride_count"]

    today_earnings = conn.execute("""
        SELECT COALESCE(SUM(bookings.fare), 0) AS earnings
        FROM bookings
        WHERE bookings.driver_id = ?
        AND bookings.status = 'Completed'
        AND date(bookings.booking_time) = date('now')
        AND EXISTS (
            SELECT 1
            FROM payments
            WHERE payments.booking_id = bookings.id
            AND payments.status = 'Paid'
            AND date(payments.payment_time) = date('now')
        )
    """, (driver_id,)).fetchone()["earnings"]

    driver_rating = conn.execute("""
        SELECT
            AVG(ratings.rating) AS average_rating,
            COUNT(ratings.id) AS rating_count
        FROM ratings
        JOIN bookings ON bookings.id = ratings.booking_id
        WHERE bookings.driver_id = ?
    """, (driver_id,)).fetchone()

    driver_profile = conn.execute("""
        SELECT
            drivers.*,
            cabs.cab_type,
            cabs.car_number
        FROM drivers
        LEFT JOIN cabs ON cabs.driver_id = drivers.id
        WHERE drivers.id = ?
        LIMIT 1
    """, (driver_id,)).fetchone()


    booking = conn.execute("""
        SELECT *
        FROM bookings
        WHERE driver_id = ?
        AND status IN ('Searching', 'Accepted', 'Ride Started')
        ORDER BY id DESC
        LIMIT 1
    """, (driver_id,)).fetchone()


    conn.close()


    return render_template(
        "driver_dashboard.html",
        booking=booking,
        today_rides=today_rides,
        today_earnings=today_earnings,
        driver_average_rating=driver_rating["average_rating"],
        driver_rating_count=driver_rating["rating_count"],
        driver_profile=driver_profile
    )


# ==========================================
# DRIVER RIDE HISTORY
# ==========================================

@app.route("/driver/rides")
def driver_rides():

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()

    rides = conn.execute("""
        SELECT
            bookings.*,
            ratings.rating,
            ratings.review,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM payments
                    WHERE payments.booking_id = bookings.id
                    AND payments.status = 'Paid'
                ) THEN 'Paid'
                ELSE 'Unpaid'
            END AS payment_status
        FROM bookings
        LEFT JOIN ratings ON ratings.booking_id = bookings.id
        WHERE bookings.driver_id = ?
        AND bookings.status = 'Completed'
        ORDER BY bookings.booking_time DESC, bookings.id DESC
    """, (driver_id,)).fetchall()

    total_completed_rides = conn.execute("""
        SELECT COUNT(*) AS ride_count
        FROM bookings
        WHERE driver_id = ?
        AND status = 'Completed'
    """, (driver_id,)).fetchone()["ride_count"]

    total_earnings = conn.execute("""
        SELECT COALESCE(SUM(bookings.fare), 0) AS earnings
        FROM bookings
        WHERE bookings.driver_id = ?
        AND bookings.status = 'Completed'
        AND EXISTS (
            SELECT 1
            FROM payments
            WHERE payments.booking_id = bookings.id
            AND payments.status = 'Paid'
        )
    """, (driver_id,)).fetchone()["earnings"]

    reviews = conn.execute("""
        SELECT
            bookings.id AS booking_id,
            bookings.booking_time,
            ratings.rating,
            ratings.review
        FROM ratings
        JOIN bookings ON bookings.id = ratings.booking_id
        WHERE bookings.driver_id = ?
        AND bookings.status = 'Completed'
        AND ratings.review IS NOT NULL
        AND TRIM(ratings.review) <> ''
        ORDER BY bookings.booking_time DESC, bookings.id DESC
    """, (driver_id,)).fetchall()

    conn.close()

    return render_template(
        "driver_rides.html",
        rides=rides,
        total_completed_rides=total_completed_rides,
        total_earnings=total_earnings,
        reviews=reviews
    )


# ==========================================
# DRIVER ACCEPT RIDE
# ==========================================

@app.route("/driver/accept/<int:booking_id>")
def accept_ride(booking_id):

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()


    conn.execute("""
        UPDATE bookings
        SET status = 'Accepted'
        WHERE id = ?
        AND driver_id = ?
        AND status = 'Searching'
    """, (booking_id, driver_id))


    conn.commit()

    conn.close()


    # Driver remains on driver dashboard
    return redirect(tab_url("driver_dashboard"))


# ==========================================
# DRIVER REJECT RIDE
# ==========================================

@app.route("/driver/reject/<int:booking_id>")
def reject_ride(booking_id):

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()


    booking = conn.execute("""
        SELECT driver_id
        FROM bookings
        WHERE id = ?
        AND driver_id = ?
        AND status = 'Accepted'
    """, (booking_id, driver_id)).fetchone()


    if booking:

        conn.execute("""
            UPDATE bookings
            SET status = 'Searching',
                driver_id = NULL
            WHERE id = ?
            AND driver_id = ?
            AND status = 'Accepted'
        """, (booking_id, driver_id))


        if booking["driver_id"]:

            conn.execute("""
                UPDATE drivers
                SET status = 'Available'
                WHERE id = ?
            """, (booking["driver_id"],))


    conn.commit()

    conn.close()


    return redirect(tab_url("driver_dashboard"))


# ==========================================
# DRIVER START RIDE
# ==========================================

@app.route("/driver/start/<int:booking_id>")
def start_ride(booking_id):

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()


    conn.execute("""
        UPDATE bookings
        SET status = 'Ride Started'
        WHERE id = ?
        AND driver_id = ?
        AND status = 'Accepted'
    """, (booking_id, driver_id))


    conn.commit()

    conn.close()


    return redirect(tab_url("driver_dashboard"))


# ==========================================
# DRIVER COMPLETE RIDE
# ==========================================

@app.route("/driver/complete/<int:booking_id>")
def complete_ride(booking_id):

    guard = driver_required()
    if guard:
        return guard

    driver_id = current_driver_id()

    conn = get_db_connection()


    booking = conn.execute("""
        SELECT driver_id
        FROM bookings
        WHERE id = ?
        AND driver_id = ?
        AND status = 'Ride Started'
    """, (booking_id, driver_id)).fetchone()


    if booking:

        # Change booking status
        # User dashboard will now show payment
        conn.execute("""
            UPDATE bookings
            SET status = 'Completed'
            WHERE id = ?
            AND driver_id = ?
            AND status = 'Ride Started'
        """, (booking_id, driver_id))


        # Make driver available again
        if booking["driver_id"]:

            conn.execute("""
                UPDATE drivers
                SET status = 'Available'
                WHERE id = ?
            """, (booking["driver_id"],))


    conn.commit()

    conn.close()


    # IMPORTANT:
    # Driver stays on driver dashboard
    return redirect(tab_url("driver_dashboard"))


# ==========================================
# PAYMENT
# ==========================================

@app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
def payment(booking_id):

    guard = user_required()
    if guard:
        return guard

    user_id = current_user_id()

    conn = get_db_connection()


    booking = conn.execute("""
        SELECT *
        FROM bookings
        WHERE id = ?
        AND user_id = ?
    """, (booking_id, user_id)).fetchone()


    if not booking:

        conn.close()

        return "Booking not found", 404

    existing_payment = conn.execute("""
        SELECT id
        FROM payments
        WHERE booking_id = ?
        AND status = 'Paid'
        LIMIT 1
    """, (booking_id,)).fetchone()

    if existing_payment:

        conn.close()

        return redirect(tab_url("book_ride", payment_error="already_paid"))


    # --------------------------------------
    # PAYMENT ONLY AFTER RIDE COMPLETED
    # --------------------------------------

    if booking["status"] != "Completed":

        conn.close()

        return "Payment is available only after the ride is completed."


    # --------------------------------------
    # PAYMENT SUBMISSION
    # --------------------------------------

    if request.method == "POST":

        payment_method = request.form["payment_method"]


        conn.execute("""
            INSERT INTO payments
            (
                booking_id,
                amount,
                payment_method,
                status,
                payment_time
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            booking_id,
            booking["fare"],
            payment_method,
            "Paid"
        ))


        conn.commit()

        conn.close()

        state = current_tab_state()
        state["active_booking_id"] = booking_id
        state["payment_success_booking_id"] = booking_id
        save_tab_state(state)

        return redirect(tab_url("book_ride"))


    conn.close()


    return render_template(
        "payment.html",
        booking=booking
    )


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    app.run(debug=True)