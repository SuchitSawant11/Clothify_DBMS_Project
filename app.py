import os
import sqlite3
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clothstore123"

DB_PATH = os.path.join(os.path.dirname(__file__), "clothify.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def rows_to_dicts(cursor):
    return [dict(row) for row in cursor.fetchall()]

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT,
            contact    TEXT,
            address    TEXT,
            date_added TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            price       REAL NOT NULL,
            quantity    INTEGER DEFAULT 0,
            category_id INTEGER REFERENCES categories(id),
            colour      TEXT,
            brand       TEXT,
            description TEXT,
            image_url   TEXT,
            supplier_id INTEGER REFERENCES suppliers(id),
            is_deleted  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS Billing (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id  INTEGER,
            total_amount REAL,
            bill_date    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS BillItems (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id    INTEGER REFERENCES Billing(id),
            product_id INTEGER REFERENCES products(id),
            unit_price REAL,
            quantity   INTEGER,
            subtotal   REAL
        );
        CREATE TABLE IF NOT EXISTS Product_Deleted_Log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            name       TEXT,
            price      REAL,
            quantity   INTEGER,
            deleted_on TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS Product_Update_Log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            field_name TEXT,
            old_value  TEXT,
            new_value  TEXT,
            updated_on TEXT DEFAULT (datetime('now'))
        );
    """)
    cur.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] == 0:
        for cat in ["Men's Wear", "Women's Wear", "Kids' Wear", "Formals", "Casuals", "Sportswear"]:
            cur.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
        now = datetime.utcnow().isoformat()
        cur.execute("INSERT INTO suppliers (name,contact,address,date_added) VALUES (?,?,?,?)",
                    ("Fashion Hub","9876543210","Mumbai, Maharashtra",now))
        cur.execute("INSERT INTO suppliers (name,contact,address,date_added) VALUES (?,?,?,?)",
                    ("Textile World","9123456789","Surat, Gujarat",now))
        cur.execute("SELECT id FROM categories WHERE name=\"Men's Wear\" LIMIT 1")
        men_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM categories WHERE name=\"Women's Wear\" LIMIT 1")
        women_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM categories WHERE name='Casuals' LIMIT 1")
        casual_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM categories WHERE name='Formals' LIMIT 1")
        formal_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM suppliers LIMIT 1")
        sup1 = cur.fetchone()["id"]
        sample = [
            ("Black Polo T-Shirt",599,25,men_id,"Black","Allen Solly","Classic black polo","/static/images/products/1763553269_Black_polo_t-shirt.jpg",sup1),
            ("Casual Shirt",799,15,men_id,"Blue","Peter England","Relaxed fit shirt","/static/images/products/1763078023_Shirt_Casual.jpg",sup1),
            ("Formal Trousers",1299,10,formal_id,"Grey","Van Heusen","Slim fit formals","/static/images/products/1763555891_formal_pant.jpg",sup1),
            ("Cargo Pants",899,20,casual_id,"Khaki","Roadster","Multi-pocket cargo","/static/images/products/1763556349_cargo.jpg",sup1),
            ("Party Wear Dress",1999,8,women_id,"Red","W","Evening party dress","/static/images/products/1763556018_party_wear.jpg",sup1),
            ("Gown",2499,5,women_id,"Navy","Aurelia","Flowy full-length gown","/static/images/products/1763556428_gown.jpg",sup1),
            ("Checks Shirt",699,18,men_id,"Multi","Levis","Plaid checks shirt","/static/images/products/1763556254_checks.jpg",sup1),
            ("Layered Shirt",849,12,women_id,"White","AND","Layered boho style","/static/images/products/1763556308_layered_shirt.jpg",sup1),
        ]
        for p in sample:
            cur.execute("INSERT INTO products (name,price,quantity,category_id,colour,brand,description,image_url,supplier_id,is_deleted) VALUES (?,?,?,?,?,?,?,?,?,0)", p)
    conn.commit()
    conn.close()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "images", "products")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {"png","jpg","jpeg","gif","webp"}

def allowed_filename(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

@app.context_processor
def inject_globals():
    user = session.get("user")
    session_user = {"username": user} if user else None
    return {"now": datetime.utcnow, "session_user": session_user, "current_year": datetime.utcnow().year}

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form["username"]
        pwd   = request.form["password"]
        if uname == "admin" and pwd == "admin123":
            session["user"] = "admin"
            flash("Welcome back, Admin! 👋", "success")
            return redirect(url_for("home"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
@login_required
def home():
    conn = get_conn(); cur = conn.cursor()
    q = request.args.get("q","").strip()
    if q:
        cur.execute("""SELECT p.id,p.name,p.price,p.quantity,p.colour,p.brand,c.name AS category,p.image_url
            FROM products p LEFT JOIN categories c ON p.category_id=c.id
            WHERE (p.name LIKE ? OR p.brand LIKE ?) AND COALESCE(p.is_deleted,0)=0""",
            (f"%{q}%",f"%{q}%"))
    else:
        cur.execute("""SELECT p.id,p.name,p.price,p.quantity,p.colour,p.brand,c.name AS category,p.image_url
            FROM products p LEFT JOIN categories c ON p.category_id=c.id
            WHERE COALESCE(p.is_deleted,0)=0""")
    products = rows_to_dicts(cur)
    cur.execute("SELECT * FROM categories")
    categories = rows_to_dicts(cur)
    conn.close()
    return render_template("home.html", products=products, categories=categories, q=q)

@app.route("/suppliers")
@login_required
def suppliers_page():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM suppliers ORDER BY id DESC")
    suppliers = rows_to_dicts(cur); conn.close()
    return render_template("suppliers.html", suppliers=suppliers)

@app.route("/suppliers/add", methods=["GET","POST"])
@login_required
def supplier_add():
    if request.method == "POST":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO suppliers (name,contact,address,date_added) VALUES (?,?,?,?)",
            (request.form.get("name"),request.form.get("contact"),request.form.get("address"),datetime.utcnow().isoformat()))
        conn.commit(); conn.close()
        flash("Supplier added ✔","success"); return redirect(url_for("suppliers_page"))
    return render_template("supplier_form.html", supplier=None)

@app.route("/suppliers/edit/<int:id>", methods=["GET","POST"])
@login_required
def supplier_edit(id):
    conn = get_conn(); cur = conn.cursor()
    if request.method == "POST":
        cur.execute("UPDATE suppliers SET name=?,contact=?,address=? WHERE id=?",
            (request.form.get("name"),request.form.get("contact"),request.form.get("address"),id))
        conn.commit(); conn.close()
        flash("Supplier updated ✔","success"); return redirect(url_for("suppliers_page"))
    cur.execute("SELECT * FROM suppliers WHERE id=?", (id,))
    supplier = dict(cur.fetchone()); conn.close()
    return render_template("supplier_form.html", supplier=supplier)

@app.route("/suppliers/delete/<int:id>", methods=["POST"])
@login_required
def supplier_delete(id):
    conn = get_conn(); conn.execute("DELETE FROM suppliers WHERE id=?", (id,)); conn.commit(); conn.close()
    flash("Supplier deleted.","info"); return redirect(url_for("suppliers_page"))

@app.route("/suppliers/<int:sid>/products")
@login_required
def supplier_products(sid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM suppliers WHERE id=?", (sid,))
    supplier = dict(cur.fetchone())
    cur.execute("""SELECT p.id,p.name,p.price,p.quantity,p.brand,p.colour,p.image_url,c.name AS category
        FROM products p LEFT JOIN categories c ON p.category_id=c.id
        WHERE p.supplier_id=? AND COALESCE(p.is_deleted,0)=0""", (sid,))
    products = rows_to_dicts(cur); conn.close()
    return render_template("supplier_products.html", supplier=supplier, products=products)

@app.route("/inventory")
@login_required
def inventory():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT p.id,p.name,p.price,p.quantity,p.is_deleted,c.name AS category
        FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.is_deleted=0""")
    products = rows_to_dicts(cur); conn.close()
    return render_template("inventory.html", products=products)

@app.route("/product/add", methods=["GET","POST"])
@login_required
def add_product():
    conn = get_conn(); cur = conn.cursor()
    if request.method == "POST":
        image_url = request.form.get("image_url","").strip()
        file = request.files.get("image_file")
        if file and file.filename and allowed_filename(file.filename):
            fname = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{fname}"
            file.save(os.path.join(UPLOAD_DIR, unique_name))
            image_url = f"/static/images/products/{unique_name}"
        d = request.form
        cur.execute("INSERT INTO products (name,price,quantity,category_id,colour,brand,description,image_url,supplier_id,is_deleted) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (d.get("name"),d.get("price"),d.get("quantity"),d.get("category_id") or None,d.get("colour"),d.get("brand"),d.get("description"),image_url,d.get("supplier_id") or None))
        conn.commit(); conn.close()
        flash("Product added ✔","success"); return redirect(url_for("inventory"))
    cur.execute("SELECT * FROM categories"); categories = rows_to_dicts(cur)
    cur.execute("SELECT * FROM suppliers"); suppliers = rows_to_dicts(cur); conn.close()
    return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)

@app.route("/product/edit/<int:pid>", methods=["GET","POST"])
@login_required
def edit_product(pid):
    conn = get_conn(); cur = conn.cursor()
    if request.method == "POST":
        cur.execute("SELECT * FROM products WHERE id=?", (pid,))
        old = dict(cur.fetchone())
        image_url = request.form.get("image_url","").strip() or old.get("image_url","")
        file = request.files.get("image_file")
        if file and file.filename and allowed_filename(file.filename):
            fname = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{fname}"
            file.save(os.path.join(UPLOAD_DIR, unique_name))
            image_url = f"/static/images/products/{unique_name}"
        d = request.form
        cur.execute("UPDATE products SET name=?,price=?,quantity=?,category_id=?,colour=?,brand=?,description=?,image_url=?,supplier_id=? WHERE id=?",
            (d.get("name"),d.get("price"),d.get("quantity"),d.get("category_id") or None,d.get("colour"),d.get("brand"),d.get("description"),image_url,d.get("supplier_id") or None,pid))
        now_str = datetime.utcnow().isoformat()
        for field in ["name","price","quantity","colour","brand"]:
            ov = str(old.get(field,"") or ""); nv = str(d.get(field,"") or "")
            if ov != nv:
                cur.execute("INSERT INTO Product_Update_Log (product_id,field_name,old_value,new_value,updated_on) VALUES (?,?,?,?,?)",(pid,field,ov,nv,now_str))
        conn.commit(); conn.close()
        flash("Product updated ✔","success"); return redirect(url_for("inventory"))
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    row = cur.fetchone(); product = dict(row) if row else None
    cur.execute("SELECT * FROM categories"); categories = rows_to_dicts(cur)
    cur.execute("SELECT * FROM suppliers"); suppliers = rows_to_dicts(cur); conn.close()
    return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)

@app.route("/product/delete/<int:pid>", methods=["POST"])
@login_required
def delete_product(pid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE products SET is_deleted=1 WHERE id=?", (pid,))
    cur.execute("SELECT id,name,price,quantity FROM products WHERE id=?", (pid,))
    row = cur.fetchone()
    if row:
        p = dict(row)
        cur.execute("INSERT INTO Product_Deleted_Log (product_id,name,price,quantity,deleted_on) VALUES (?,?,?,?,?)",
            (p["id"],p["name"],p["price"],p["quantity"],datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    flash("Product moved to Deleted Products.","info"); return redirect(url_for("inventory"))

@app.route("/product/restore/<int:pid>", methods=["POST"])
@login_required
def restore_product(pid):
    conn = get_conn(); conn.execute("UPDATE products SET is_deleted=0 WHERE id=?", (pid,)); conn.commit(); conn.close()
    flash("Product restored ✔","success"); return redirect(url_for("deleted_products"))

@app.route("/products/deleted")
@login_required
def deleted_products():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM Product_Deleted_Log ORDER BY deleted_on DESC")
    deleted = rows_to_dicts(cur); conn.close()
    return render_template("deleted_products.html", deleted=deleted)

@app.route("/products/updates")
@login_required
def updated_products():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM Product_Update_Log ORDER BY updated_on DESC")
    logs = rows_to_dicts(cur); conn.close()
    return render_template("updated_products.html", logs=logs)

@app.route("/categories", methods=["GET","POST"])
@login_required
def categories_page():
    conn = get_conn(); cur = conn.cursor()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if name:
            try:
                cur.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                conn.commit(); flash(f'Category "{name}" added ✔',"success")
            except sqlite3.IntegrityError:
                flash("Category already exists.","danger")
        return redirect(url_for("categories_page"))
    cur.execute("""SELECT c.id,c.name,COUNT(p.id) AS total_products,COALESCE(SUM(p.quantity),0) AS total_quantity
        FROM categories c LEFT JOIN products p ON p.category_id=c.id AND COALESCE(p.is_deleted,0)=0
        GROUP BY c.id,c.name ORDER BY c.name""")
    categories = rows_to_dicts(cur); conn.close()
    return render_template("categories.html", categories=categories)

@app.route("/billing")
@login_required
def billing():
    bill_items = session.get("bill_items",[])
    total = sum(float(i["subtotal"]) for i in bill_items)
    return render_template("billing.html", bill_items=bill_items, total_amount=total)

@app.route("/bill/add/<int:pid>")
@login_required
def bill_add(pid):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    row = cur.fetchone(); conn.close()
    if not row: flash("Product not found.","danger"); return redirect(url_for("home"))
    p = dict(row)
    items = session.get("bill_items",[])
    for item in items:
        if item["id"] == pid:
            item["qty"] += 1; item["subtotal"] = round(item["unit_price"]*item["qty"],2)
            session["bill_items"] = items; return redirect(url_for("billing"))
    items.append({"id":p["id"],"name":p["name"],"unit_price":float(p["price"]),"qty":1,"subtotal":float(p["price"])})
    session["bill_items"] = items; return redirect(url_for("billing"))

@app.route("/bill/remove/<int:pid>")
@login_required
def bill_remove(pid):
    session["bill_items"] = [i for i in session.get("bill_items",[]) if i["id"] != pid]
    return redirect(url_for("billing"))

@app.route("/bill/clear")
@login_required
def bill_clear():
    session["bill_items"] = []; return redirect(url_for("billing"))

@app.route("/bill/save", methods=["POST"])
@login_required
def bill_save():
    items = request.json.get("items",[])
    if not items: return jsonify({"success":False,"message":"Cart is empty."})
    conn = get_conn(); cur = conn.cursor()
    total = sum(float(x["subtotal"]) for x in items)
    cur.execute("INSERT INTO Billing (customer_id,total_amount,bill_date) VALUES (?,?,?)",(None,total,datetime.utcnow().isoformat()))
    bill_id = cur.lastrowid
    for item in items:
        cur.execute("INSERT INTO BillItems (bill_id,product_id,unit_price,quantity,subtotal) VALUES (?,?,?,?,?)",
            (bill_id,item["id"],item["unit_price"],item["qty"],item["subtotal"]))
        cur.execute("SELECT quantity FROM products WHERE id=?", (item["id"],))
        row = cur.fetchone()
        if row: cur.execute("UPDATE products SET quantity=? WHERE id=?", (max(0,row["quantity"]-item["qty"]),item["id"]))
    conn.commit(); conn.close()
    session["bill_items"] = []
    return jsonify({"success":True,"bill_id":bill_id})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
