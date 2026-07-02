# Sprint 1 Demo Script

**Project:** E-Invoice API Ecosystem — API Publisher Tool  
**Team:** 26T2-9900-H19B-BREAD  
**Demo Scope:** Sprint 1 (18 June – 2 July 2026)

---

## 1. Opening (about 1 minute)

> Hello everyone. We are team H19B BREAD.
> Today we will show you what we built in Sprint 1.
>
> The problem we are solving is this:
> Inside large companies, there are many APIs for e-invoicing.
> But these APIs are poorly documented, use different formats, and have no standard review process.
> This makes it very hard for developers to find and reuse them.
>
> Our solution is the **API Publisher Tool**.
> It works as a quality gate for the e-invoicing API system.
> Enterprise publishers can use it to submit, validate, and manage their e-invoicing APIs.
>
> In Sprint 1, we focused on six user stories:
> user login, spec file upload, metadata form, spec validation, validation feedback,
> and draft saving with resubmission.
>
> Let us start the demo now.

---

## 2. FR-1 — Publisher Login and Access Control (H19BBREAD-1)

**User Story:** As an enterprise publisher, I want to log in before using the API Publisher Tool, so that only approved users can submit or remove APIs.

### Steps

1. **Open the browser and go to `http://localhost:5173/homepage` directly.**

   > You can see the system redirects us to the login page right away.
   > Users who are not logged in cannot access any publishing feature.
   > This matches the acceptance criteria: users must log in before using the tool.

2. **Try to log in with a wrong password.**

   > The system shows a clear error message.
   > This matches: when access is denied, the user sees a clear message.

3. **Log in with the correct account.**
   ```
   Email:    publisher@example.com
   Password: password123
   ```

   > After login, the system takes us to the Publisher Dashboard.
   > The login token is saved locally, so if we refresh the page, we stay logged in.
   > This matches: only users who have logged in can access the publishing functions.

4. **(Optional) Show the Register page.**

   > After a new user registers, the system logs them in right away.
   > No need to go back to the login page.

---

## 3. FR-10 — API List on Dashboard (H19BBREAD-10)

> Before we show the submit process, let us look at the main dashboard.

**User Story:** As an enterprise publisher, I want to see a list of APIs my enterprise has published, so I can check their status and manage them.

### Steps

1. **Point to the table on the dashboard.**

   > This table shows all APIs for the current enterprise.
   > Each row has the API name, protocol type, endpoint URL, and current status.
   > The data comes from the backend in real time.
   > Only APIs from this enterprise are shown — other companies' data is not visible.

2. **Point to the colored status tags.**

   > Each status uses a different color:
   > - Green = Published
   > - Red = Rejected
   > - Yellow = Draft
   > - Blue with spin = Validating
   > - Gray = Withdrawn

3. **Hover over a long API name or URL.**

   > When the text is too long to show in the column, hover to see the full text in a tooltip.

---

## 4. FR-2 + FR-3 — Spec Upload and Metadata Form (H19BBREAD-2 & 3)

Click the **"Publish New API"** button in the top right to open the three-step form.

**FR-2 User Story:** As a publisher, I want to upload a spec file or provide a URL, so I can submit my REST or SOAP API for review and publishing.

**FR-3 User Story:** As a publisher, I want to fill in structured metadata for my API, so the API can be validated, found, and used by other services.

### Step 1 — Import Spec

1. **Select Protocol: REST.**

   > The tool supports REST APIs using OpenAPI or Swagger format,
   > and SOAP APIs using WSDL format.

2. **Upload a spec file — use `case1.json`.**

   > Drag and drop the file, or click to browse.
   > The system reads the file and fills in the form fields for us automatically.
   > This matches FR-2: the uploaded spec is stored as part of the submission record.

3. **Show the error message for unsupported file types.**

   > Now let us try to upload a `.pdf` file.
   > The system blocks it right away and shows a red error message,
   > telling us which formats are allowed.
   > This matches FR-2: the system shows an error when an unsupported file is attached.

4. **Show the URL mode.**

   > Switch to "Enter URL" and type a hosted spec address.
   > Due to browser security rules, we may not be able to read the file directly.
   > But when we submit, the backend will fetch the spec from that URL by itself.
   > So the URL mode works correctly for the final submission.

5. **Click Continue to go to Step 2.**

### Step 2 — Review and Edit

1. **Show the auto-filled fields.**

   > You can see many fields are already filled in from the spec file —
   > API name, endpoint URL, protocol, input and output format, and more.
   > Fields filled by the system are marked with a green "Auto" tag.
   > This matches FR-3: a standard metadata collection process is provided.

2. **Point to the required fields.**

   > All key fields are required: name, endpoint, protocol, formats, auth method, description, and category.
   > If any required field is empty, the system blocks the next step and highlights the empty field.
   > This matches FR-3: required fields are clearly shown, and incomplete submissions cannot go forward.

3. **Show the "Save as Draft" button (FR-9 preview).**

   > If a publisher is not ready to submit yet, they can click "Save as Draft".
   > The system saves the current spec and metadata to the database with a Draft status.
   > The modal closes, and a yellow Draft row appears in the dashboard table.
   > We will talk more about draft support shortly.

4. **Fill in any missing fields and click "Validate and Publish" to go to Step 3.**

---

## 5. FR-4 + FR-7 — Spec Validation and Feedback (H19BBREAD-4 & 5)

**FR-4 User Story:** As a publisher, I want the system to validate my spec file, so that invalid documents are caught before publishing.

**FR-7 User Story:** As a publisher, I want clear validation feedback after submitting, so I know which steps passed or failed and how to fix the issues.

### Scenario A — Validation Fails

1. **Submit a spec file that has missing required fields on purpose.**

   > The system runs three validation steps in order:
   > - Step 1: Spec Validation — checks the structure and format of the spec file
   > - Step 2: E-invoicing Domain Check — checks if the API matches e-invoicing standards
   > - Step 3: Security Metadata Check — checks if the auth method is complete and correct

2. **Show the failure result.**

   > Step 1 fails. The system shows a red result with a detailed error message —
   > it tells us exactly which field is missing and where in the spec.
   > This matches FR-4: the system detects missing elements and shows a detailed error report.

3. **Point to the gray steps below.**

   > Steps 2 and 3 are shown in gray, with a dash and the message "Not evaluated — step above failed."
   > This is different from a red failure — it means these steps were not run, not that they failed.
   > This matches FR-7: the results clearly show which steps passed, which failed, and which were skipped.

4. **Click "Fix and Resubmit".**

   > The system goes back to Step 1.
   > The publisher can upload a new file or change the info and try again.
   > This matches FR-9: if validation fails, the publisher can fix and resubmit.

### Scenario B — Validation Passes

1. **Submit `case1.json`, a valid OpenAPI spec.**

2. **Show the three green steps.**

   > All three steps show a green pass result.
   > This matches FR-4: valid specs can move forward through the submission process.

3. **Show the success result.**

   > A green "API Published Successfully" message appears, with the Submission ID.
   > This matches FR-7: the publisher receives clear feedback when the API is published.

4. **Close the modal and look at the dashboard.**

   > A new row with a green "Published" tag appears in the table.
   > The list refreshes on its own — no need to reload the page.

---

## 6. FR-9 — Draft Saving and Resubmission (H19BBREAD-6)

**User Story:** As a publisher, I want to save incomplete submissions as drafts and resubmit corrected APIs after failure, so I do not have to start over every time.

### What we already showed:

- **Save as Draft** button in Step 2 saves the spec and metadata to the database.
- **Fix and Resubmit** after a failed validation takes the publisher back to Step 1.
- The dashboard table shows the correct status for each API: Draft, Rejected, or Published.

> These match the acceptance criteria:
> the system allows saving drafts, and publishers can fix and resubmit after a failure.
> The status is always up to date in the table.

---

## 7. FR-11 (Partial) — API Withdrawal

**User Story:** As a publisher, I want to withdraw a published API, so that outdated or incorrect APIs can be removed from the system.

### Steps

1. **Find a Published API row and click the red withdraw button.**

   > A confirm dialog appears to prevent accidental clicks.

2. **Confirm the withdrawal.**

   > The backend updates the status. The table refreshes and the row now shows gray "Withdrawn".
   > This matches: withdrawn APIs are no longer available. The publisher sees a success message.

3. **Point to the disabled withdraw button.**

   > Once withdrawn, the button is grayed out. Hovering shows "Already withdrawn."

---

## 8. Closing (about 1 minute)

> Let us quickly review what we completed in Sprint 1.
>
> | User Story | Status |
> |---|---|
> | FR-1 Login and Access Control | Done |
> | FR-2 Spec File Upload | Done |
> | FR-3 Metadata Form | Done |
> | FR-4 Spec Validation | Done |
> | FR-7 Validation Feedback | Done |
> | FR-9 Draft Saving and Resubmission | Done |
> | FR-10 API List (Backlog item) | Done early |
> | FR-11 Withdrawal (partial) | Done early |
>
> For Sprint 2, we plan to work on:
> - Stronger domain and security validation rules (FR-5, FR-6)
> - Full Central API Repository integration (FR-8)
> - Update API and edit draft features (FR-11)
> - Unified UI with Discovery and Composition services (FR-12)
>
> Thank you for listening. We are happy to take any questions.

---

## Before the Demo — Checklist

- [ ] Docker Desktop is running, container `sprint1-db` is active
- [ ] Backend is running: `uvicorn app.main:app --reload` (port 8000)
- [ ] Frontend is running: `npm run dev` (port 5173)
- [ ] Database is set up: `24.6_DATABASE_1stversion.sql` has been run
- [ ] Test account works: `publisher@example.com` / `password123`
- [ ] Test files are ready: `frontend/src/mock/case1.json` (valid spec) and a broken spec file for the failure demo
- [ ] Browser localStorage is cleared so the demo starts from the logged-out state
