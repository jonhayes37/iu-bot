CREATE TABLE IF NOT EXISTS role_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assignable_roles (
    role_id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL,
    role_name TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES role_categories (category_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS role_aliases (
    alias TEXT PRIMARY KEY,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (role_id) REFERENCES assignable_roles (role_id) ON DELETE CASCADE
);