"""
Google Sheets service — list spreadsheets, get tabs, manage subscriptions.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User
from models.subscription import SheetSubscription
from schemas.subscription import SpreadsheetInfo, SheetTab
from services.auth import get_valid_google_token


@dataclass(slots=True)
class SheetSnapshot:
    spreadsheet_id: str
    spreadsheet_name: str
    sheet_name: str
    sheet_gid: str | None
    headers: list[str]
    rows: list[dict[str, object]]
    fetched_at: datetime


async def list_user_spreadsheets(user: User, db: AsyncSession) -> list[SpreadsheetInfo]:
    """List Google Sheets owned by or shared with the user."""
    access_token = await get_valid_google_token(user, db)
    if not access_token:
        return []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                "fields": "files(id,name,webViewLink)",
                "pageSize": 100,
                "orderBy": "modifiedTime desc",
            },
        )
        if response.status_code != 200:
            return []

        data = response.json()
        return [
            SpreadsheetInfo(
                id=f["id"],
                name=f["name"],
                url=f.get("webViewLink", f"https://docs.google.com/spreadsheets/d/{f['id']}"),
            )
            for f in data.get("files", [])
        ]


async def get_spreadsheet_tabs(
    user: User, db: AsyncSession, spreadsheet_id: str
) -> list[SheetTab]:
    """Get all sheet tabs in a spreadsheet."""
    access_token = await get_valid_google_token(user, db)
    if not access_token:
        return []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "sheets.properties"},
        )
        if response.status_code != 200:
            return []

        data = response.json()
        return [
            SheetTab(
                title=sheet["properties"]["title"],
                sheet_id=sheet["properties"]["sheetId"],
                index=sheet["properties"]["index"],
            )
            for sheet in data.get("sheets", [])
        ]


async def get_spreadsheet_metadata(
    user: User, db: AsyncSession, spreadsheet_id: str
) -> dict[str, object]:
    """Fetch spreadsheet metadata and available sheet tabs."""
    access_token = await get_valid_google_token(user, db)
    if not access_token:
        return {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "includeGridData": False,
                "fields": "spreadsheetId,properties.title,sheets.properties",
            },
        )
        if response.status_code != 200:
            return {}

        return response.json()


async def get_sheet_snapshot(
    user: User,
    db: AsyncSession,
    spreadsheet_id: str,
    sheet_name: str,
) -> SheetSnapshot | None:
    """Fetch a simplified snapshot for a single sheet/tab."""
    access_token = await get_valid_google_token(user, db)
    if not access_token:
        return None

    metadata = await get_spreadsheet_metadata(user, db, spreadsheet_id)
    if not metadata:
        return None

    sheets = metadata.get("sheets", []) or []
    target_sheet = next(
        (
            sheet.get("properties", {})
            for sheet in sheets
            if sheet.get("properties", {}).get("title") == sheet_name
        ),
        None,
    )
    if not target_sheet:
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(sheet_name, safe='')}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"},
        )
        if response.status_code != 200:
            return None

        values = response.json().get("values", []) or []
        if not values:
            return SheetSnapshot(
                spreadsheet_id=spreadsheet_id,
                spreadsheet_name=metadata.get("properties", {}).get("title", spreadsheet_id),
                sheet_name=sheet_name,
                sheet_gid=str(target_sheet.get("sheetId")) if target_sheet.get("sheetId") is not None else None,
                headers=[],
                rows=[],
                fetched_at=datetime.now(timezone.utc),
            )

        headers = [
            str(value).strip() if str(value).strip() else f"Column {index + 1}"
            for index, value in enumerate(values[0])
        ]
        rows: list[dict[str, object]] = []
        for row_index, row_values in enumerate(values[1:], start=2):
            row_data: dict[str, object] = {"_row_number": row_index}
            for index, header in enumerate(headers):
                row_data[header] = row_values[index] if index < len(row_values) else None
            rows.append(row_data)

        return SheetSnapshot(
            spreadsheet_id=spreadsheet_id,
            spreadsheet_name=metadata.get("properties", {}).get("title", spreadsheet_id),
            sheet_name=sheet_name,
            sheet_gid=str(target_sheet.get("sheetId")) if target_sheet.get("sheetId") is not None else None,
            headers=headers,
            rows=rows,
            fetched_at=datetime.now(timezone.utc),
        )


async def get_spreadsheet_snapshots(
    user: User,
    db: AsyncSession,
    spreadsheet_id: str,
    monitored_sheet_names: Optional[list[str]] = None,
) -> list[SheetSnapshot]:
    """Fetch snapshots for all or selected sheets in a spreadsheet."""
    metadata = await get_spreadsheet_metadata(user, db, spreadsheet_id)
    if not metadata:
        return []

    sheets = metadata.get("sheets", []) or []
    sheet_names = [
        sheet.get("properties", {}).get("title")
        for sheet in sheets
        if sheet.get("properties", {}).get("title")
    ]
    if monitored_sheet_names:
        wanted = set(monitored_sheet_names)
        sheet_names = [name for name in sheet_names if name in wanted]

    snapshots: list[SheetSnapshot] = []
    for sheet_name in sheet_names:
        snapshot = await get_sheet_snapshot(user, db, spreadsheet_id, sheet_name)
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


async def create_subscription(
    db: AsyncSession,
    user: User,
    spreadsheet_id: str,
    sheet_name: Optional[str] = None,
    spreadsheet_name: Optional[str] = None,
    spreadsheet_url: Optional[str] = None,
    sheet_gid: Optional[str] = None,
    notification_template: Optional[str] = None,
    polling_enabled: bool = True,
    polling_interval_minutes: int = 1,
    track_all_sheets: bool = False,
    monitored_sheet_names: Optional[list[str]] = None,
) -> SheetSubscription:
    """Create a new sheet subscription for a user."""
    stored_sheet_name = sheet_name or ("*" if track_all_sheets else "")
    if not stored_sheet_name:
        raise ValueError("sheet_name is required unless track_all_sheets is enabled")

    subscription = SheetSubscription(
        user_id=user.id,
        spreadsheet_id=spreadsheet_id,
        spreadsheet_name=spreadsheet_name,
        spreadsheet_url=spreadsheet_url,
        sheet_name=stored_sheet_name,
        sheet_gid=sheet_gid,
        notification_template=notification_template,
        polling_enabled=polling_enabled,
        polling_interval_minutes=polling_interval_minutes,
        track_all_sheets=track_all_sheets,
        monitored_sheet_names=monitored_sheet_names,
    )
    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)
    return subscription


async def get_user_subscriptions(
    db: AsyncSession, user_id: uuid.UUID
) -> list[SheetSubscription]:
    """Get all subscriptions for a user."""
    result = await db.execute(
        select(SheetSubscription)
        .where(SheetSubscription.user_id == user_id)
        .order_by(SheetSubscription.created_at.desc())
    )
    return list(result.scalars().all())


async def get_subscription_by_id(
    db: AsyncSession, subscription_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[SheetSubscription]:
    """Get a specific subscription belonging to a user."""
    result = await db.execute(
        select(SheetSubscription).where(
            SheetSubscription.id == subscription_id,
            SheetSubscription.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_subscription(
    db: AsyncSession, subscription_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Delete a subscription. Returns True if deleted."""
    result = await db.execute(
        delete(SheetSubscription).where(
            SheetSubscription.id == subscription_id,
            SheetSubscription.user_id == user_id,
        )
    )
    return result.rowcount > 0


def generate_apps_script(
    webhook_url: str, webhook_secret: str, sheet_name: str
) -> str:
    """Generate Google Apps Script code for the user to install."""
    return f'''// ============================================
// SheetNotify — Auto-generated Apps Script
// Install this in your Google Sheet's Script Editor
// (Extensions → Apps Script)
// ============================================

const WEBHOOK_URL = "{webhook_url}";
const WEBHOOK_SECRET = "{webhook_secret}";
const SHEET_NAME = "{sheet_name}";

function onChange(e) {{
  try {{
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    if (!sheet) return;

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return; // Skip if only header row

    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const rowData = sheet.getRange(lastRow, 1, 1, sheet.getLastColumn()).getValues()[0];

    const data = {{}};
    headers.forEach((header, i) => {{
      if (header) data[header.toString().trim()] = rowData[i];
    }});

    const payload = {{
      spreadsheet_id: SpreadsheetApp.getActiveSpreadsheet().getId(),
      spreadsheet_name: SpreadsheetApp.getActiveSpreadsheet().getName(),
      sheet_name: SHEET_NAME,
      row_number: lastRow,
      row_data: data,
      timestamp: new Date().toISOString(),
    }};

    UrlFetchApp.fetch(WEBHOOK_URL, {{
      method: "POST",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    }});

  }} catch (error) {{
    console.error("SheetNotify Error:", error);
  }}
}}

// ============================================
// SETUP: Run this function ONCE to create the trigger
// ============================================
function setupTrigger() {{
  // Remove existing triggers first
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => ScriptApp.deleteTrigger(trigger));

  // Create new onChange trigger
  ScriptApp.newTrigger("onChange")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();

  Logger.log("✅ SheetNotify trigger installed successfully!");
}}
'''
