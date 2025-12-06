from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change in production

DB_NAME = "bus_booking.db"


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and insert sample data if DB does not exist."""
    if os.path.exists(DB_NAME):
        return  # DB already exists, keep existing data

    conn = get_db_connection()
    cur = conn.cursor()

    # Create buses table
    cur.execute(
        """
        CREATE TABLE buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_name TEXT NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            arrival_time TEXT NOT NULL,
            total_seats INTEGER NOT NULL,
            fare REAL NOT NULL
        );
        """
    )

    # Create bookings table
    cur.execute(
        """
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_id INTEGER NOT NULL,
            passenger_name TEXT NOT NULL,
            passenger_email TEXT NOT NULL,
            journey_date TEXT NOT NULL,
            seats_booked INTEGER NOT NULL,
            booking_time TEXT NOT NULL,
            FOREIGN KEY(bus_id) REFERENCES buses(id)
        );
        """
    )

    # ---------- Generate 20 routes × 10 buses each ----------
    # (fares inside each route go from low -> high)
    routes = [
        ("Delhi", "Jaipur", "DJ"),
        ("Delhi", "Lucknow", "DL"),
        ("Delhi", "Agra", "DA"),
        ("Delhi", "Chandigarh", "DC"),
        ("Delhi", "Mumbai", "DM"),
        ("Jaipur", "Udaipur", "JU"),
        ("Jaipur", "Jodhpur", "JJ"),
        ("Jaipur", "Delhi", "JD"),
        ("Mumbai", "Pune", "MP"),
        ("Mumbai", "Goa", "MG"),
        ("Mumbai", "Nashik", "MN"),
        ("Pune", "Mumbai", "PM"),
        ("Pune", "Bangalore", "PB"),
        ("Lucknow", "Kanpur", "LK"),
        ("Lucknow", "Varanasi", "LV"),
        ("Agra", "Delhi", "AD"),
        ("Chandigarh", "Delhi", "CD"),
        ("Bangalore", "Chennai", "BC"),
        ("Chennai", "Bangalore", "CB"),
        ("Hyderabad", "Bangalore", "HB"),
    ]

    tier_names = [
        "Budget Express",
        "Morning Express",
        "Super Saver",
        "Day Rider",
        "AC Seater",
        "Volvo Comfort",
        "Semi Sleeper",
        "Evening Rider",
        "Premium Sleeper",
        "Royal Volvo",
    ]

    sample_buses = []

    for route_index, (src, dst, code) in enumerate(routes):
        base_fare = 200 + route_index * 40  # each route slightly more expensive

        for i in range(10):
            name = f"{code} {tier_names[i]}"

            # simple pattern for departure/arrival times
            dep_hour = 5 + i * 2  # 05:00, 07:00, ..., 23:00
            arr_hour = (dep_hour + 4 + (i % 3)) % 24  # travel time 4–6 hours

            departure_time = f"{dep_hour:02d}:00"
            arrival_time = f"{arr_hour:02d}:00"

            total_seats = 40 + (i % 5) * 2  # 40, 42, 44, 46, 48

            fare = float(base_fare + i * 30)  # strictly increasing inside route

            sample_buses.append(
                (
                    name,
                    src,
                    dst,
                    departure_time,
                    arrival_time,
                    total_seats,
                    fare,
                )
            )

    cur.executemany(
        """
        INSERT INTO buses
        (bus_name, source, destination, departure_time, arrival_time, total_seats, fare)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        sample_buses,
    )

    conn.commit()
    conn.close()
    print("Database initialized with 20 routes and 200 buses.")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        source = request.form.get("source", "").strip()
        destination = request.form.get("destination", "").strip()
        journey_date = request.form.get("journey_date")

        if not source or not destination or not journey_date:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("index"))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM buses
            WHERE LOWER(source) = LOWER(?) AND LOWER(destination) = LOWER(?)
            ORDER BY fare ASC;
            """,
            (source, destination),
        )
        buses = cur.fetchall()
        conn.close()

        if not buses:
            flash("No buses found for this route.", "warning")
            return redirect(url_for("index"))

        return render_template(
            "search_results.html",
            buses=buses,
            journey_date=journey_date,
            source=source,
            destination=destination,
        )

    return render_template("index.html")


def get_available_seats(bus_id, journey_date):
    conn = get_db_connection()
    cur = conn.cursor()

    # total seats
    cur.execute("SELECT total_seats FROM buses WHERE id = ?;", (bus_id,))
    bus = cur.fetchone()
    if not bus:
        conn.close()
        return 0

    total_seats = bus["total_seats"]

    # already booked for that date
    cur.execute(
        """
        SELECT COALESCE(SUM(seats_booked), 0) AS booked
        FROM bookings
        WHERE bus_id = ? AND journey_date = ?;
        """,
        (bus_id, journey_date),
    )
    row = cur.fetchone()
    booked = row["booked"] if row else 0

    conn.close()
    return total_seats - booked


@app.route("/book/<int:bus_id>", methods=["GET", "POST"])
def book(bus_id):
    journey_date = request.args.get("journey_date")
    if not journey_date:
        flash("Journey date is required.", "danger")
        return redirect(url_for("index"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM buses WHERE id = ?;", (bus_id,))
    bus = cur.fetchone()
    conn.close()

    if not bus:
        flash("Bus not found.", "danger")
        return redirect(url_for("index"))

    available_seats = get_available_seats(bus_id, journey_date)

    if request.method == "POST":
        passenger_name = request.form.get("passenger_name", "").strip()
        passenger_email = request.form.get("passenger_email", "").strip()
        seats_raw = request.form.get("seats_booked", "0")

        try:
            seats_booked = int(seats_raw)
        except ValueError:
            seats_booked = 0

        if seats_booked <= 0:
            flash("Seats must be at least 1.", "danger")
            return redirect(url_for("book", bus_id=bus_id, journey_date=journey_date))

        if seats_booked > available_seats:
            flash(f"Only {available_seats} seats are available.", "danger")
            return redirect(url_for("book", bus_id=bus_id, journey_date=journey_date))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bookings
            (bus_id, passenger_name, passenger_email, journey_date, seats_booked, booking_time)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                bus_id,
                passenger_name,
                passenger_email,
                journey_date,
                seats_booked,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        booking_id = cur.lastrowid
        conn.close()

        flash("Booking successful!", "success")
        return redirect(url_for("confirmation", booking_id=booking_id))

    return render_template(
        "booking.html",
        bus=bus,
        journey_date=journey_date,
        available_seats=available_seats,
    )


@app.route("/confirmation/<int:booking_id>")
def confirmation(booking_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.bus_name, b.source, b.destination, b.departure_time, b.arrival_time,
               b.fare, bk.*
        FROM bookings bk
        JOIN buses b ON b.id = bk.bus_id
        WHERE bk.id = ?;
        """,
        (booking_id,),
    )
    booking = cur.fetchone()
    conn.close()

    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("index"))

    return render_template("confirmation.html", booking=booking)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
