# E-invoicing API Publisher Database Setup

This README explains how to recreate the local PostgreSQL database for the API Publisher project.

## 1. Start PostgreSQL with Docker

Make sure Docker Desktop is running, then execute:

```bash
docker run --name sprint1-db \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -p 5432:5432 \
  -d postgres
```

If a container with the same name already exists, start it with:

```bash
docker start sprint1-db
```

## 2. Database connection settings

Use the following connection details in DBeaver or backend configuration:

| Item | Value |
|---|---|
| Database Type | PostgreSQL |
| Host | localhost |
| Port | 5432 |
| Database | postgres |
| Username | postgres |
| Password | mysecretpassword |

Recommended connection string:

```text
postgresql://postgres:mysecretpassword@localhost:5432/postgres
```

## 3. Run the database schema script in DBeaver

1. Open DBeaver.
2. Create a PostgreSQL connection using the settings above.
3. Open `init_all_tables.sql`.
4. Run the whole script using `Alt + X` or the `Execute SQL Script` button.
5. Refresh the database navigator.
6. Confirm that the tables have been created.

Expected main tables include:

```text
enterprise
app_user
api_submission
api_version
api_specification
auth_metadata
validation_run
validation_result
schema_mapping
```

## 4. Notes for backend development

- The script includes `DROP ... CASCADE`, so it can be re-run during local development.
- The script includes sample data for basic testing.
- Do not store plain-text passwords in production code. Passwords should be hashed before insertion into `app_user.password_hash`.
- Do not modify the schema locally without notifying the database owner. Schema changes should be shared through an agreed SQL migration or update script.

## 5. Common issues

### Port 5432 is already in use

Another PostgreSQL instance may already be running. Either stop the existing service or map Docker to another local port, for example:

```bash
docker run --name sprint1-db \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -p 5433:5432 \
  -d postgres
```

Then use port `5433` in DBeaver and backend configuration.

### Connection refused

Check that Docker Desktop is running and the database container is active:

```bash
docker ps
```

If the container is stopped, run:

```bash
docker start sprint1-db
```

### Container name already exists

Start the existing container:

```bash
docker start sprint1-db
```

Or remove and recreate it:

```bash
docker rm sprint1-db
```
