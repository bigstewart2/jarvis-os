from datetime import datetime, timedelta, timezone


class GoogleCalendarClient:
    def __init__(self, service):
        self._service = service

    def list_events(self, days_ahead: int = 1) -> list[dict]:
        now = datetime.now(timezone.utc)
        response = self._service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days_ahead)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=25,
        ).execute()

        events = []
        for item in response.get("items", []):
            events.append({
                "title": item.get("summary", "(no title)"),
                "start": item["start"].get("dateTime", item["start"].get("date", "")),
                "end": item["end"].get("dateTime", item["end"].get("date", "")),
                "location": item.get("location", ""),
                "attendee_count": len(item.get("attendees", [])),
            })
        return events

    def create_event(self, title: str, start_iso: str, end_iso: str, description: str = "") -> dict:
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        created = self._service.events().insert(calendarId="primary", body=body).execute()
        return {
            "event_id": created["id"],
            "html_link": created.get("htmlLink", ""),
            "title": created.get("summary", title),
            "start": created.get("start", {}).get("dateTime", start_iso),
            "end": created.get("end", {}).get("dateTime", end_iso),
        }
