CREATE TABLE notification_dismissals (
 owner_id INTEGER NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
 notification_id TEXT NOT NULL CHECK(length(notification_id) BETWEEN 1 AND 150),
 dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(owner_id, notification_id)
);
