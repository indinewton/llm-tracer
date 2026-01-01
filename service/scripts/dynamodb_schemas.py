"""DynamoDB table schemas."""

from typing import TypedDict, List


# Type definitions for clarity
class KeySchemaElement(TypedDict):
    AttributeName: str
    KeyType: str  # 'HASH' or 'RANGE'


class AttributionDefinition(TypedDict):
    AttributeName: str
    AttributeType: str  # 'S' (string) or 'N' (number) or 'B' (binary)


class Projection(TypedDict):
    ProjectionType: str  # 'ALL' or 'INCLUDE' or 'KEYS_ONLY'


class GSI(TypedDict):
    IndexName: str
    KeySchema: List[KeySchemaElement]
    Projection: Projection


class TableSchema(TypedDict):
    KeySchema: List[KeySchemaElement]
    AttributeDefinitions: List[AttributionDefinition]
    GlobalSecondaryIndexes: List[GSI]
    BillingMode: str  # 'PROVISIONED' or 'PAY_PER_REQUEST'


# === Traces Table Schema ===
TRACES_SCHEMA: TableSchema = {
    'KeySchema': [
        {'AttributeName': 'trace_id', 'KeyType': 'HASH'}
    ],
    'AttributeDefinitions': [
        {'AttributeName': 'trace_id', 'AttributeType': 'S'},
        {'AttributeName': 'project_id', 'AttributeType': 'S'},
        {'AttributeName': 'start_time', 'AttributeType': 'S'},
    ],
    'GlobalSecondaryIndexes': [
        {
            'IndexName': 'project-time-index',
            'KeySchema': [
                {'AttributeName': 'project_id', 'KeyType': 'HASH'},
                {'AttributeName': 'start_time', 'KeyType': 'RANGE'}
            ],
            'Projection': {'ProjectionType': 'ALL'},
        }
    ],
    'BillingMode': 'PAY_PER_REQUEST',
}


# === Spans Table Schema ===
SPANS_SCHEMA: TableSchema = {
    'KeySchema': [
        {'AttributeName': 'span_id', 'KeyType': 'HASH'}
    ],
    'AttributeDefinitions': [
        {'AttributeName': 'span_id', 'AttributeType': 'S'},
        {'AttributeName': 'trace_id', 'AttributeType': 'S'},
    ],
    'GlobalSecondaryIndexes': [
        {
            'IndexName': 'trace-index',
            'KeySchema': [
                {'AttributeName': 'trace_id', 'KeyType': 'HASH'},
            ],
            'Projection': {'ProjectionType': 'ALL'},
        }
    ],
    'BillingMode': 'PAY_PER_REQUEST',
}


# === TTL Config ===
TTL_CONFIG = {
    'AttributeName': 'ttl',
    'Enabled': True,
}

def get_create_table_kwargs(
    table_name: str,
    schema: TableSchema
) -> dict:
    """Built kwargs dict for dynamodb.create_table()"""
    return {'TableName': table_name, **schema}
