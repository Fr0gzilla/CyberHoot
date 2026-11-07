CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE `role` (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(20) NOT NULL, 
    label VARCHAR(50) NOT NULL, 
    CONSTRAINT pk_role PRIMARY KEY (id), 
    CONSTRAINT uq_role_name UNIQUE (name)
);

CREATE TABLE user (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    username VARCHAR(32) NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    is_enabled BOOL NOT NULL, 
    email_verified_at DATETIME, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    last_login_at DATETIME, 
    failed_logins INTEGER NOT NULL, 
    locked_until DATETIME, 
    session_token VARCHAR(32) NOT NULL, 
    CONSTRAINT pk_user PRIMARY KEY (id), 
    CONSTRAINT ck_user_failed_logins_positif CHECK (failed_logins >= 0), 
    CONSTRAINT uq_user_email UNIQUE (email), 
    CONSTRAINT uq_user_username UNIQUE (username)
);

CREATE TABLE account_token (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    purpose ENUM('activation','reset') NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL, 
    expires_at DATETIME NOT NULL, 
    used_at DATETIME, 
    CONSTRAINT pk_account_token PRIMARY KEY (id), 
    CONSTRAINT fk_account_token_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_account_token_token_hash UNIQUE (token_hash)
);

CREATE INDEX ix_account_token_user_id ON account_token (user_id);

CREATE TABLE user_role (
    user_id INTEGER NOT NULL, 
    role_id INTEGER NOT NULL, 
    CONSTRAINT pk_user_role PRIMARY KEY (user_id, role_id), 
    CONSTRAINT fk_user_role_role_id_role FOREIGN KEY(role_id) REFERENCES `role` (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_role_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE
);

INSERT INTO `role` (id, name, label) VALUES (1, 'player', 'Joueur');

INSERT INTO `role` (id, name, label) VALUES (2, 'creator', 'Créateur');

INSERT INTO `role` (id, name, label) VALUES (3, 'admin', 'Administrateur');

INSERT INTO alembic_version (version_num) VALUES ('0001');

