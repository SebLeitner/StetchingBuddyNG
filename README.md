# Stretch Coach Infrastruktur & Speech API

Dieses Repository enthält die statische Stretch-Coach-Anwendung sowie die Infrastrukturdefinition für Hosting und Sprachsynthese.

## Architekturüberblick

- **Frontend**: Statische Web-App (HTML/CSS/JS) im Verzeichnis `frontend/`, ausgeliefert über S3 und CloudFront.
- **Speech Backend**: AWS Lambda (Python) hinter einem HTTP API Gateway-Endpunkt. Die Funktion ruft Amazon Polly (`SynthesizeSpeech`) auf und liefert MP3-Audio als binäre Antwort an den Client. Die Infrastruktur liegt in `infra/terraform/`.

## Speech API Contract

- **HTTP-Methode**: `POST`
- **Pfad**: `/api/speak`
- **Request-Body (JSON)**:
  ```json
  {
    "text": "Zu sprechender Inhalt",
    "language": "de-DE",
    "voice": "Vicki"
  }
  ```
  - `text` (Pflichtfeld): Beliebiger Deutschsprachiger Text (max. 1500 Zeichen).
  - `language` (optional): Standard `de-DE`.
  - `voice` (optional): Polly VoiceId, Standard `Vicki` (de-DE).
- **Antwort**: MP3-Audio (`Content-Type: audio/mpeg`). Fehler werden als JSON `{ "error": "..." }` mit passendem Statuscode geliefert.

Die Lambda-Funktion akzeptiert auch JSON-Antworten von Polly-Tasks (z. B. `audioUrl` oder `audioBase64`) für zukünftige Erweiterungen.

## Exercises API Contract

- **Basis-URL**: `${APIGATEWAY_INVOKE_URL}/api/exercises`
- **Antwortformat**: Alle Endpunkte liefern JSON mit CORS-Headern. Fehler werden als `{ "error": "…" }` ausgegeben.
- **Endpunkte**:
  - `GET /api/exercises`: Liefert `{ "items": [ … ], "count": <number> }` ohne Test-Übungen.
  - `GET /api/exercises/{id}`: Einzelne Übung nach `id`.
  - `POST /api/exercises`: Legt eine neue Übung an. Pflichtfelder: `id`, `name`, `instruction`, `sets` (>= 1). Optionale Felder wie `prep_time`, `duration`, `rep_time`, `rest_time`, `mindfulness`, `break_bell` werden übernommen, leere Strings werden ignoriert.
  - `PUT /api/exercises/{id}`: Aktualisiert eine bestehende Übung. Ein optionales Feld `previousId` erlaubt das Umbenennen (Ändern der `id`).
  - `DELETE /api/exercises/{id}`: Löscht eine Übung. "Test"-IDs werden serverseitig abgefangen.
- **Validierungsregeln**: Numerische Felder müssen Ganzzahlen sein (`sets` > 0, übrige Werte >= 0). Test-Übungen (`test`, `test übung`, `testübung`) werden weder gespeichert noch ausgeliefert.

Zur Erstbefüllung dient `scripts/import_exercises.py`, das die bestehende `frontend/exercises.json` in die neue DynamoDB-Tabelle schreibt (`python scripts/import_exercises.py --table <TABELLE>`).

## Frontend-Integration

- Die Funktion `speak()` in `frontend/index.html` ruft den Speech-Endpunkt auf, lädt das MP3 als Blob und spielt es über ein `Audio`-Objekt ab.
- Während der Wiedergabe sind `skip` und `stop` aktiv, `AbortController` bricht laufende Requests ab. Bei Netzwerk- oder AWS-Fehlern erfolgt ein Fallback auf die lokale `speechSynthesis` API.
- Die produktive Instanz bindet `frontend/config.production.js` ein. Darin wird `window.STRETCH_COACH_CONFIG` bereits mit den Live-Werten befüllt:
  ```js
  window.STRETCH_COACH_CONFIG = {
    appUrl: "https://sbuddy.leitnersoft.com",
    bucketName: "sbuddy.leitnersoft.com",
    cloudFrontDomain: "d1spztj11put9r.cloudfront.net",
    speechApiUrl: "https://hr9yi4qsmg.execute-api.us-east-1.amazonaws.com/api/speak",
    speechLambdaArn: "arn:aws:lambda:us-east-1:140023375269:function:stretch-coach-speech",
  };
  ```
  Lokale Tests können weiterhin ein eigenes `window.STRETCH_COACH_CONFIG` setzen; es überschreibt die Werte aus der Produktionsdatei.
  Neue Parameter:
  - `progressApiUrl`: Endpunkt für Übungsfortschrittsdaten (`/api/exercise-completions`).
  - `exercisesApiUrl`: Endpunkt für den Übungskatalog (`/api/exercises`).

## Infrastruktur & Deployment

1. **Terraform vorbereiten**
   ```bash
   cd infra/terraform
   terraform init
   terraform apply
   ```
   Provisioniert werden S3, CloudFront, Route53-Einträge, ACM-Zertifikat, die Polly-Lambda-Funktion, IAM-Rollen/-Policies sowie der API-Gateway-Endpunkt.

2. **Frontend deployen**
   ```bash
   ./manual-deploy.sh path/zur/.env
   ```
   Erwartete Variablen (`.env`):
   ```env
   AWS_REGION=eu-central-1
   S3_BUCKET=sbuddy.leitnersoft.com
   CLOUDFRONT_DISTRIBUTION_ID=E123...
   SPEECH_API_ENDPOINT=https://abc.execute-api.us-east-1.amazonaws.com/api/speak
   SOURCE_DIR=frontend
   ```
   `frontend/deploy.sh` gibt den gesetzten Speech-Endpunkt aus und synchronisiert HTML/CSS/JS/Assets.

3. **Secrets & IAM**
   - AWS-Zugang per Terraform-Backend oder lokalem Profile (keine Zugangsdaten im Code).
   - Die Lambda-Rolle erhält nur `polly:SynthesizeSpeech`/`StartSpeechSynthesisTask` sowie CloudWatch-Logs.
   - CORS ist auf die Produktiv-Domain begrenzt; bei weiteren Clients `CORS_ALLOW_ORIGIN` in Terraform anpassen.

## Tests

- Manuelle End-to-End-Tests: Übungen starten, Skip/Stop prüfen, Netzwerkfehler simulieren.
- Terraform-Plan/Test via `terraform plan`.
- Frontend im Browser mit/ohne Speech API testen, um den Fallback sicherzustellen.
