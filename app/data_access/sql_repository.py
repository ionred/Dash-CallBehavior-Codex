"""SQL Server data access layer."""
from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pyodbc

from config import AppConfig, DatabaseConfig

logger = logging.getLogger(__name__)


@dataclass
class EventListing:
    event_name: str
    subgroup: str
    event_date: str
    monitor_start: str
    monitor_end: str
    description: str


@dataclass
class AccountRecord:
    account_number: str


@dataclass
class CallHistoryRecord:
    queue_name: str
    talk_time: float
    call_date: str


class SqlRepository:
    """Encapsulates SQL Server database operations."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _connect(self, db_config: DatabaseConfig) -> pyodbc.Connection:
        logger.debug("Opening connection to %s/%s", db_config.server, db_config.database)
        connection = pyodbc.connect(
            db_config.connection_string(),
            timeout=db_config.timeout_seconds,
            autocommit=False,
        )
        connection.timeout = db_config.timeout_seconds
        return connection

    @contextlib.contextmanager
    def _cursor(self, db_config: DatabaseConfig) -> Iterable[pyodbc.Cursor]:
        connection = self._connect(db_config)
        try:
            cursor = connection.cursor()
            cursor.timeout = db_config.timeout_seconds
            yield cursor
            connection.commit()
        except pyodbc.OperationalError as exc:  # timeout or network failure
            connection.rollback()
            logger.exception("Operational error executing SQL: %s", exc)
            raise
        except Exception:
            connection.rollback()
            logger.exception("Unhandled SQL error")
            raise
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def fetch_event_listings(self) -> List[EventListing]:
        query = (
            "SELECT eventName, subGroup, eventDate, monitorStart, monitorEnd, Description "
            "FROM dbo.eventListings"
        )
        records: List[EventListing] = []
        with self._cursor(self._config.event_db) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                records.append(
                    EventListing(
                        event_name=row.eventName,
                        subgroup=row.subGroup,
                        event_date=str(row.eventDate),
                        monitor_start=str(row.monitorStart),
                        monitor_end=str(row.monitorEnd),
                        description=row.Description,
                    )
                )
        return records

    def fetch_accounts(self, event_name: str, subgroup: str) -> List[AccountRecord]:
        query = (
            "SELECT DISTINCT accountNumber "
            "FROM dbo.eventAccounts "
            "WHERE eventName = ? AND subGroup = ?"
        )
        with self._cursor(self._config.event_db) as cursor:
            cursor.execute(query, (event_name, subgroup))
            rows = cursor.fetchall()
            return [AccountRecord(account_number=row.accountNumber) for row in rows]

    def insert_temp_accounts(self, account_numbers: Sequence[str]) -> str:
        temp_table_name = f"#accountNumbers_{uuid.uuid4().hex}"
        create_sql = f"CREATE TABLE {temp_table_name} (accountNumber NVARCHAR(15) PRIMARY KEY)"
        insert_sql = f"INSERT INTO {temp_table_name} (accountNumber) VALUES (?)"

        with self._cursor(self._config.temp_db) as cursor:
            cursor.execute(create_sql)
            cursor.fast_executemany = True
            cursor.timeout = self._config.bulk_insert_timeout_seconds
            data = [(account,) for account in account_numbers]
            chunk_size = 1000
            for index in range(0, len(data), chunk_size):
                chunk = data[index : index + chunk_size]
                cursor.executemany(insert_sql, chunk)
        return temp_table_name

    def query_call_history(
        self,
        temp_table_name: str,
        start_date: str,
        end_date: str,
    ) -> List[CallHistoryRecord]:
        query = f"""
            SELECT callhist.queueName, callhist.TalkTime, callhist.CallDate
            FROM dbo.callHistory AS callhist
            INNER JOIN {temp_table_name} AS accounts ON callhist.accountNumber = accounts.accountNumber
            WHERE callhist.CallDate BETWEEN ? AND ?
        """
        records: List[CallHistoryRecord] = []
        with self._cursor(self._config.call_history_db) as cursor:
            cursor.execute(query, (start_date, end_date))
            rows = cursor.fetchall()
            for row in rows:
                records.append(
                    CallHistoryRecord(
                        queue_name=row.queueName,
                        talk_time=float(row.TalkTime or 0),
                        call_date=str(row.CallDate),
                    )
                )
        return records

    # ------------------------------------------------------------------
    # Event creation workflow helpers
    # ------------------------------------------------------------------
    def begin_transaction(self) -> pyodbc.Connection:
        connection = self._connect(self._config.event_db)
        return connection

    def commit(self, connection: pyodbc.Connection) -> None:
        connection.commit()
        connection.close()

    def rollback(self, connection: pyodbc.Connection) -> None:
        connection.rollback()
        connection.close()

    def event_exists(self, connection: pyodbc.Connection, event_name: str, subgroup: str) -> bool:
        query = (
            "SELECT COUNT(1) FROM dbo.eventListings WHERE eventName = ? AND subGroup = ?"
        )
        cursor = connection.cursor()
        cursor.execute(query, (event_name, subgroup))
        return cursor.fetchone()[0] > 0

    def count_event_accounts(
        self, connection: pyodbc.Connection, event_name: str, subgroup: str
    ) -> int:
        query = (
            "SELECT COUNT(1) FROM dbo.eventAccounts WHERE eventName = ? AND subGroup = ?"
        )
        cursor = connection.cursor()
        cursor.execute(query, (event_name, subgroup))
        return cursor.fetchone()[0]

    def get_event_account_count(self, event_name: str, subgroup: str) -> int:
        query = "SELECT COUNT(1) FROM dbo.eventAccounts WHERE eventName = ? AND subGroup = ?"
        with self._cursor(self._config.event_db) as cursor:
            cursor.execute(query, (event_name, subgroup))
            return cursor.fetchone()[0]

    def delete_event_listing(self, connection: pyodbc.Connection, event_name: str, subgroup: str) -> None:
        query = "DELETE FROM dbo.eventListings WHERE eventName = ? AND subGroup = ?"
        cursor = connection.cursor()
        cursor.execute(query, (event_name, subgroup))

    def upsert_event_listing(
        self,
        connection: pyodbc.Connection,
        event_name: str,
        subgroup: str,
        event_date: str,
        monitor_start: str,
        monitor_end: str,
        description: str,
    ) -> None:
        delete_sql = "DELETE FROM dbo.eventListings WHERE eventName = ? AND subGroup = ?"
        insert_sql = (
            "INSERT INTO dbo.eventListings (eventName, subGroup, eventDate, monitorStart, monitorEnd, Description) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        cursor = connection.cursor()
        cursor.execute(delete_sql, (event_name, subgroup))
        cursor.execute(
            insert_sql,
            (event_name, subgroup, event_date, monitor_start, monitor_end, description),
        )

    def delete_event_accounts(self, connection: pyodbc.Connection, event_name: str, subgroup: str) -> None:
        query = "DELETE FROM dbo.eventAccounts WHERE eventName = ? AND subGroup = ?"
        cursor = connection.cursor()
        cursor.execute(query, (event_name, subgroup))

    def insert_event_accounts(
        self,
        connection: pyodbc.Connection,
        event_name: str,
        subgroup: str,
        account_numbers: Sequence[str],
    ) -> None:
        insert_sql = (
            "INSERT INTO dbo.eventAccounts (eventName, subGroup, accountNumber) VALUES (?, ?, ?)"
        )
        cursor = connection.cursor()
        cursor.fast_executemany = True
        cursor.timeout = self._config.bulk_insert_timeout_seconds
        data = [(event_name, subgroup, acc) for acc in account_numbers]
        chunk_size = 1000
        for index in range(0, len(data), chunk_size):
            chunk = data[index : index + chunk_size]
            cursor.executemany(insert_sql, chunk)

    def append_event_accounts(
        self,
        connection: pyodbc.Connection,
        event_name: str,
        subgroup: str,
        account_numbers: Sequence[str],
    ) -> None:
        insert_sql = (
            "INSERT INTO dbo.eventAccounts (eventName, subGroup, accountNumber) "
            "SELECT ?, ?, ? WHERE NOT EXISTS ("
            "SELECT 1 FROM dbo.eventAccounts ea WHERE ea.eventName = ? AND ea.subGroup = ? AND ea.accountNumber = ?"
            ")"
        )
        cursor = connection.cursor()
        cursor.timeout = self._config.bulk_insert_timeout_seconds
        for account in account_numbers:
            cursor.execute(insert_sql, (event_name, subgroup, account, event_name, subgroup, account))

    def delete_member_research(self, connection: pyodbc.Connection, event_name: str, subgroup: str) -> None:
        query = "DELETE FROM dbo.memberResearch WHERE eventName = ? AND subGroup = ?"
        cursor = connection.cursor()
        cursor.execute(query, (event_name, subgroup))

    def insert_member_research(
        self,
        connection: pyodbc.Connection,
        records: Sequence[tuple[str, str, str, str, int, float]],
    ) -> None:
        insert_sql = (
            "INSERT INTO dbo.memberResearch "
            "(eventName, subGroup, queueName, callDate, callCount, averageTalkTime) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        cursor = connection.cursor()
        cursor.fast_executemany = True
        cursor.execute("SET NOCOUNT ON")
        cursor.executemany(insert_sql, records)

