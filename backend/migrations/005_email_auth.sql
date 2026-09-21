CREATE TABLE email_challenges (
 purpose TEXT NOT NULL CHECK(purpose IN ('signup','reset','change_email_old','change_email_new','change_password')),
 destination TEXT NOT NULL, code_hash TEXT NOT NULL, salt TEXT NOT NULL,
 payload TEXT NOT NULL DEFAULT '', expires_at INTEGER NOT NULL,
 sent_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
 PRIMARY KEY(purpose,destination)
);
CREATE TABLE email_send_attempts (
 address TEXT NOT NULL, attempted_at INTEGER NOT NULL
);
CREATE INDEX email_send_attempts_time ON email_send_attempts(attempted_at);
