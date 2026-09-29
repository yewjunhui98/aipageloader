IF OBJECT_ID('dbo.users', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.users (
        id INT IDENTITY(1,1) PRIMARY KEY,
        username NVARCHAR(100) UNIQUE NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF OBJECT_ID('dbo.pages', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.pages (
        id INT IDENTITY(1,1) PRIMARY KEY,
        url NVARCHAR(500) UNIQUE NOT NULL,
        title NVARCHAR(200) NOT NULL,
        content NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF OBJECT_ID('dbo.page_visits', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.page_visits (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL,
        page_id INT NOT NULL,
        visited_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_page_visits_users FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT FK_page_visits_pages FOREIGN KEY (page_id) REFERENCES dbo.pages(id)
    );

    CREATE INDEX IX_page_visits_user_time ON dbo.page_visits (user_id, visited_at);
END;

IF OBJECT_ID('dbo.user_transition_models', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_transition_models (
        user_id INT PRIMARY KEY,
        model_type NVARCHAR(50) NOT NULL,
        model_payload NVARCHAR(MAX) NOT NULL,
        trained_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_transition_models_users FOREIGN KEY (user_id) REFERENCES dbo.users(id)
    );
END;

IF OBJECT_ID('dbo.user_prediction_snapshots', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_prediction_snapshots (
        user_id INT NOT NULL,
        current_url NVARCHAR(500) NOT NULL,
        predictions_payload NVARCHAR(MAX) NOT NULL,
        generated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        PRIMARY KEY (user_id, current_url),
        CONSTRAINT FK_prediction_snapshots_users FOREIGN KEY (user_id) REFERENCES dbo.users(id)
    );
END;
