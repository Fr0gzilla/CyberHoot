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

-- Running upgrade 0001 -> 0002

CREATE TABLE category (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    slug VARCHAR(40) NOT NULL, 
    name VARCHAR(80) NOT NULL, 
    description VARCHAR(255) NOT NULL, 
    position INTEGER NOT NULL, 
    CONSTRAINT pk_category PRIMARY KEY (id), 
    CONSTRAINT uq_category_slug UNIQUE (slug)
);

CREATE TABLE media (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    uid VARCHAR(32) NOT NULL, 
    owner_id INTEGER, 
    mime_type VARCHAR(30) NOT NULL, 
    size INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    status ENUM('pending','clean','rejected') NOT NULL, 
    scan_detail VARCHAR(255), 
    created_at DATETIME NOT NULL, 
    scanned_at DATETIME, 
    CONSTRAINT pk_media PRIMARY KEY (id), 
    CONSTRAINT fk_media_owner_id_user FOREIGN KEY(owner_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT uq_media_uid UNIQUE (uid)
);

CREATE INDEX ix_media_owner_id ON media (owner_id);

CREATE INDEX ix_media_sha256 ON media (sha256);

CREATE INDEX ix_media_status ON media (status);

CREATE TABLE quiz (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    creator_id INTEGER, 
    category_id INTEGER NOT NULL, 
    title VARCHAR(120) NOT NULL, 
    description VARCHAR(500) NOT NULL, 
    difficulty ENUM('easy','medium','hard') NOT NULL, 
    status ENUM('draft','pending','published','rejected') NOT NULL, 
    rejection_reason VARCHAR(500), 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    submitted_at DATETIME, 
    published_at DATETIME, 
    CONSTRAINT pk_quiz PRIMARY KEY (id), 
    CONSTRAINT fk_quiz_category_id_category FOREIGN KEY(category_id) REFERENCES category (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_quiz_creator_id_user FOREIGN KEY(creator_id) REFERENCES user (id) ON DELETE SET NULL
);

CREATE INDEX ix_quiz_category_id ON quiz (category_id);

CREATE INDEX ix_quiz_creator_id ON quiz (creator_id);

CREATE INDEX ix_quiz_status ON quiz (status);

CREATE TABLE play_session (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    token VARCHAR(43) NOT NULL, 
    user_id INTEGER, 
    quiz_id INTEGER NOT NULL, 
    question_ids JSON NOT NULL, 
    current_index INTEGER NOT NULL, 
    score INTEGER NOT NULL, 
    total INTEGER NOT NULL, 
    started_at DATETIME NOT NULL, 
    finished_at DATETIME, 
    CONSTRAINT pk_play_session PRIMARY KEY (id), 
    CONSTRAINT ck_play_session_index_positif CHECK (current_index >= 0), 
    CONSTRAINT ck_play_session_score_positif CHECK (score >= 0), 
    CONSTRAINT fk_play_session_quiz_id_quiz FOREIGN KEY(quiz_id) REFERENCES quiz (id) ON DELETE CASCADE, 
    CONSTRAINT fk_play_session_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT uq_play_session_token UNIQUE (token)
);

CREATE INDEX ix_play_session_quiz_id ON play_session (quiz_id);

CREATE INDEX ix_play_session_user_id ON play_session (user_id);

CREATE TABLE question (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    quiz_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    text VARCHAR(500) NOT NULL, 
    explanation TEXT NOT NULL, 
    media_id INTEGER, 
    media_alt VARCHAR(200), 
    CONSTRAINT pk_question PRIMARY KEY (id), 
    CONSTRAINT fk_question_media_id_media FOREIGN KEY(media_id) REFERENCES media (id) ON DELETE SET NULL, 
    CONSTRAINT fk_question_quiz_id_quiz FOREIGN KEY(quiz_id) REFERENCES quiz (id) ON DELETE CASCADE, 
    CONSTRAINT quiz_position UNIQUE (quiz_id, position)
);

CREATE TABLE review (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    quiz_id INTEGER NOT NULL, 
    rating INTEGER NOT NULL, 
    comment VARCHAR(1000), 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    CONSTRAINT pk_review PRIMARY KEY (id), 
    CONSTRAINT ck_review_note_1_a_5 CHECK (rating BETWEEN 1 AND 5), 
    CONSTRAINT fk_review_quiz_id_quiz FOREIGN KEY(quiz_id) REFERENCES quiz (id) ON DELETE CASCADE, 
    CONSTRAINT fk_review_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE, 
    CONSTRAINT un_avis_par_joueur UNIQUE (user_id, quiz_id)
);

CREATE INDEX ix_review_quiz_id ON review (quiz_id);

CREATE TABLE answer_option (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    question_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    text VARCHAR(300) NOT NULL, 
    is_correct BOOL NOT NULL, 
    CONSTRAINT pk_answer_option PRIMARY KEY (id), 
    CONSTRAINT fk_answer_option_question_id_question FOREIGN KEY(question_id) REFERENCES question (id) ON DELETE CASCADE, 
    CONSTRAINT question_position UNIQUE (question_id, position)
);

CREATE TABLE play_answer (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    session_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    question_id INTEGER, 
    selected_ids JSON NOT NULL, 
    is_correct BOOL NOT NULL, 
    answered_at DATETIME NOT NULL, 
    CONSTRAINT pk_play_answer PRIMARY KEY (id), 
    CONSTRAINT fk_play_answer_question_id_question FOREIGN KEY(question_id) REFERENCES question (id) ON DELETE SET NULL, 
    CONSTRAINT fk_play_answer_session_id_play_session FOREIGN KEY(session_id) REFERENCES play_session (id) ON DELETE CASCADE, 
    CONSTRAINT session_position UNIQUE (session_id, position)
);

CREATE INDEX ix_play_answer_question_id ON play_answer (question_id);

INSERT INTO category (id, slug, name, description, position) VALUES (1, 'hameconnage', 'Hameçonnage et ingénierie sociale', 'Repérer les faux messages, appels et sites qui cherchent à vous manipuler.', 1);

INSERT INTO category (id, slug, name, description, position) VALUES (2, 'mots-de-passe', 'Mots de passe et authentification', 'Choisir, retenir et protéger ses mots de passe ; la double authentification.', 2);

INSERT INTO category (id, slug, name, description, position) VALUES (3, 'securite-web', 'Sécurité web', 'Naviguer prudemment : HTTPS, téléchargements, extensions, failles courantes.', 3);

INSERT INTO category (id, slug, name, description, position) VALUES (4, 'logiciels-malveillants', 'Logiciels malveillants', 'Virus, rançongiciels, chevaux de Troie : comment ils arrivent et comment s''en protéger.', 4);

INSERT INTO category (id, slug, name, description, position) VALUES (5, 'reseaux-wifi', 'Réseaux et Wi-Fi', 'Wi-Fi public, box, VPN : sécuriser ses connexions.', 5);

INSERT INTO category (id, slug, name, description, position) VALUES (6, 'donnees-rgpd', 'Données personnelles et RGPD', 'Protéger sa vie privée et connaître ses droits.', 6);

INSERT INTO category (id, slug, name, description, position) VALUES (7, 'cryptographie', 'Cryptographie', 'Chiffrement, signatures, certificats : les bases expliquées simplement.', 7);

INSERT INTO category (id, slug, name, description, position) VALUES (8, 'bonnes-pratiques', 'Bonnes pratiques au quotidien', 'Mises à jour, sauvegardes, verrouillage : les gestes qui protègent.', 8);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE live_game (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    pin VARCHAR(6), 
    host_id INTEGER, 
    quiz_id INTEGER NOT NULL, 
    status ENUM('lobby','question','paused','reveal','finished') NOT NULL, 
    question_ids JSON NOT NULL, 
    current_index INTEGER NOT NULL, 
    time_limit INTEGER NOT NULL, 
    max_players INTEGER NOT NULL, 
    question_started_at DATETIME, 
    question_deadline DATETIME, 
    paused_remaining_ms INTEGER, 
    version INTEGER NOT NULL, 
    created_at DATETIME NOT NULL, 
    last_activity_at DATETIME NOT NULL, 
    ended_at DATETIME, 
    CONSTRAINT pk_live_game PRIMARY KEY (id), 
    CONSTRAINT fk_live_game_host_id_user FOREIGN KEY(host_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT fk_live_game_quiz_id_quiz FOREIGN KEY(quiz_id) REFERENCES quiz (id) ON DELETE CASCADE, 
    CONSTRAINT uq_live_game_pin UNIQUE (pin)
);

CREATE INDEX ix_live_game_host_id ON live_game (host_id);

CREATE INDEX ix_live_game_quiz_id ON live_game (quiz_id);

CREATE TABLE live_player (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    game_id INTEGER NOT NULL, 
    user_id INTEGER, 
    nickname VARCHAR(20) NOT NULL, 
    nickname_key VARCHAR(20) NOT NULL, 
    token VARCHAR(43) NOT NULL, 
    score INTEGER NOT NULL, 
    kicked BOOL NOT NULL, 
    joined_at DATETIME NOT NULL, 
    CONSTRAINT pk_live_player PRIMARY KEY (id), 
    CONSTRAINT fk_live_player_game_id_live_game FOREIGN KEY(game_id) REFERENCES live_game (id) ON DELETE CASCADE, 
    CONSTRAINT fk_live_player_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT pseudo_unique UNIQUE (game_id, nickname_key), 
    CONSTRAINT uq_live_player_token UNIQUE (token)
);

CREATE INDEX ix_live_player_game_id ON live_player (game_id);

CREATE TABLE live_answer (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    game_id INTEGER NOT NULL, 
    player_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    question_id INTEGER, 
    selected_ids JSON NOT NULL, 
    is_correct BOOL NOT NULL, 
    points INTEGER NOT NULL, 
    elapsed_ms INTEGER NOT NULL, 
    answered_at DATETIME NOT NULL, 
    CONSTRAINT pk_live_answer PRIMARY KEY (id), 
    CONSTRAINT fk_live_answer_game_id_live_game FOREIGN KEY(game_id) REFERENCES live_game (id) ON DELETE CASCADE, 
    CONSTRAINT fk_live_answer_player_id_live_player FOREIGN KEY(player_id) REFERENCES live_player (id) ON DELETE CASCADE, 
    CONSTRAINT fk_live_answer_question_id_question FOREIGN KEY(question_id) REFERENCES question (id) ON DELETE SET NULL, 
    CONSTRAINT une_reponse_par_question UNIQUE (player_id, position)
);

CREATE INDEX ix_live_answer_game_id ON live_answer (game_id);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE badge (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    code VARCHAR(40) NOT NULL, 
    name VARCHAR(80) NOT NULL, 
    description VARCHAR(255) NOT NULL, 
    icon VARCHAR(8) NOT NULL, 
    rule ENUM('parties','sans_faute','zero','serie','expert','animateur','vainqueur','createur') NOT NULL, 
    threshold INTEGER NOT NULL, 
    category_id INTEGER, 
    position INTEGER NOT NULL, 
    CONSTRAINT pk_badge PRIMARY KEY (id), 
    CONSTRAINT fk_badge_category_id_category FOREIGN KEY(category_id) REFERENCES category (id) ON DELETE CASCADE, 
    CONSTRAINT uq_badge_code UNIQUE (code)
);

CREATE TABLE user_badge (
    user_id INTEGER NOT NULL, 
    badge_id INTEGER NOT NULL, 
    obtained_at DATETIME NOT NULL, 
    CONSTRAINT pk_user_badge PRIMARY KEY (user_id, badge_id), 
    CONSTRAINT fk_user_badge_badge_id_badge FOREIGN KEY(badge_id) REFERENCES badge (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_badge_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE
);

ALTER TABLE question ADD COLUMN kind ENUM('choice','true_false','phishing','order') NOT NULL DEFAULT 'choice';

ALTER TABLE question ADD COLUMN payload JSON;

ALTER TABLE question ALTER COLUMN kind DROP DEFAULT;

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (1, 'premiere-partie', 'Premier clic', 'Terminer sa toute première partie.', '🐣', 'parties', 1, NULL, 1);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (2, 'habitue', 'Habitué du quiz', 'Terminer 10 parties.', '🎮', 'parties', 10, NULL, 2);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (3, 'accro', 'Pare-feu humain', 'Terminer 50 parties.', '🧱', 'parties', 50, NULL, 3);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (4, 'zero-faille', 'Zéro faille', 'Réussir sans aucune erreur une partie d''au moins 5 questions.', '🛡️', 'sans_faute', 5, NULL, 4);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (5, 'maillon-faible', 'Maillon faible (pour l''instant)', 'Finir une partie d''au moins 5 questions… sans une seule bonne réponse. Ça arrive aux meilleurs.', '🙈', 'zero', 5, NULL, 5);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (6, 'patch-du-jour', 'Patch du jour', 'Jouer 3 jours de suite.', '📅', 'serie', 3, NULL, 6);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (7, 'mise-a-jour-hebdo', 'Mise à jour hebdomadaire', 'Jouer 7 jours de suite.', '🔁', 'serie', 7, NULL, 7);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (8, 'expert-hameconnage', 'Pêcheur repenti', '80 % de bonnes réponses sur au moins 20 questions d''hameçonnage.', '🎣', 'expert', 20, 1, 8);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (9, 'expert-mots-de-passe', 'Coffre-fort ambulant', '80 % de bonnes réponses sur au moins 20 questions de mots de passe.', '🔐', 'expert', 20, 2, 9);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (10, 'expert-web', 'Gardien du cadenas', '80 % de bonnes réponses sur au moins 20 questions de sécurité web.', '🌐', 'expert', 20, 3, 10);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (11, 'expert-malware', 'Chasseur de rançongiciels', '80 % de bonnes réponses sur au moins 20 questions de logiciels malveillants.', '🦠', 'expert', 20, 4, 11);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (12, 'expert-reseaux', 'Ondes maîtrisées', '80 % de bonnes réponses sur au moins 20 questions de réseaux et Wi-Fi.', '📶', 'expert', 20, 5, 12);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (13, 'expert-rgpd', 'Délégué à la vie privée', '80 % de bonnes réponses sur au moins 20 questions de données personnelles.', '🕵️', 'expert', 20, 6, 13);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (14, 'expert-crypto', 'Casseur de César', '80 % de bonnes réponses sur au moins 20 questions de cryptographie.', '🗝️', 'expert', 20, 7, 14);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (15, 'expert-pratiques', 'Hygiène numérique', '80 % de bonnes réponses sur au moins 20 questions de bonnes pratiques.', '🧼', 'expert', 20, 8, 15);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (16, 'animateur', 'Maître de cérémonie', 'Animer une partie en direct d''au moins 3 joueurs.', '🎤', 'animateur', 1, NULL, 16);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (17, 'vainqueur', 'Champion de la salle', 'Finir premier d''une partie en direct d''au moins 3 joueurs.', '🏆', 'vainqueur', 1, NULL, 17);

INSERT INTO badge (id, code, name, description, icon, rule, threshold, category_id, position) VALUES (18, 'auteur', 'Auteur publié', 'Voir un de ses quiz publié.', '✍️', 'createur', 1, NULL, 18);

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

CREATE TABLE audit_log (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    created_at DATETIME NOT NULL, 
    user_id INTEGER, 
    username VARCHAR(32), 
    ip VARCHAR(45), 
    action VARCHAR(40) NOT NULL, 
    target VARCHAR(120), 
    details JSON, 
    CONSTRAINT pk_audit_log PRIMARY KEY (id), 
    CONSTRAINT fk_audit_log_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_log_action ON audit_log (action);

CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);

CREATE INDEX ix_audit_log_user_id ON audit_log (user_id);

CREATE TABLE recovery_code (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    code_hash VARCHAR(64) NOT NULL, 
    used_at DATETIME, 
    CONSTRAINT pk_recovery_code PRIMARY KEY (id), 
    CONSTRAINT fk_recovery_code_user_id_user FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_recovery_code_code_hash UNIQUE (code_hash)
);

CREATE INDEX ix_recovery_code_user_id ON recovery_code (user_id);

CREATE TABLE report (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    reporter_id INTEGER, 
    quiz_id INTEGER, 
    review_id INTEGER, 
    reason VARCHAR(500) NOT NULL, 
    status ENUM('open','closed') NOT NULL, 
    created_at DATETIME NOT NULL, 
    handled_at DATETIME, 
    handled_by_id INTEGER, 
    resolution VARCHAR(255), 
    CONSTRAINT pk_report PRIMARY KEY (id), 
    CONSTRAINT fk_report_handled_by_id_user FOREIGN KEY(handled_by_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT fk_report_quiz_id_quiz FOREIGN KEY(quiz_id) REFERENCES quiz (id) ON DELETE CASCADE, 
    CONSTRAINT fk_report_reporter_id_user FOREIGN KEY(reporter_id) REFERENCES user (id) ON DELETE SET NULL, 
    CONSTRAINT fk_report_review_id_review FOREIGN KEY(review_id) REFERENCES review (id) ON DELETE CASCADE
);

CREATE INDEX ix_report_quiz_id ON report (quiz_id);

CREATE INDEX ix_report_status ON report (status);

ALTER TABLE user ADD COLUMN totp_secret VARCHAR(255);

ALTER TABLE user ADD COLUMN totp_enabled_at DATETIME;

ALTER TABLE user ADD COLUMN totp_last_step INTEGER;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

