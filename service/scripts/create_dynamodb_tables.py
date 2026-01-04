#!/usr/bin/env python3
"""Create DyanmoDB tables for local testing."""

import argparse
import sys
import os
import boto3
from botocore.exceptions import ClientError

# Add scripts directory to path for direct execution;
#  mainly for automation scripts using jutsfiles
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynamodb_schemas import (
    TRACES_SCHEMA,
    SPANS_SCHEMA,
    TTL_CONFIG,
    get_create_table_kwargs,
)


def create_tables(
    endpoint_url=None,
    region='eu-central-1',
    traces_table='llm-tracer-dev-traces',
    spans_table='llm-tracer-dev-spans',
):
    """Create DyanmoDB tables.
    
    Parameters
    ----------
    endpoint_url : str
        The endpoint URL for the DynamoDB service (None for AWS, 
        http://localhost:8000 for local)
    region : str
        AWS region
    traces_table : str
        Name of traces table
    spans_table : str
        Name of spans table
    """
    kwargs = {"region_name": region}

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"
        print(f"Using DynamoDB Local at {endpoint_url}")
    else:
        print(f"Creating tables in AWS DynamoDB in {region}")

    dynamodb = boto3.resource('dynamodb', **kwargs)

    # create traces table
    try:
        traces = dynamodb.create_table(**get_create_table_kwargs(traces_table, TRACES_SCHEMA))

        if endpoint_url:
            traces.wait_until_exists()
        
        print(f"  Created traces table: {traces_table}")

        # Enable TTL (AWS Only)
        if not endpoint_url:
            try:
                client = boto3.client('dynamodb', region_name=region)
                client.update_time_to_live(
                    TableName=traces_table,
                    TimeToLiveSpecification=TTL_CONFIG,
                )
                print("  Enabled TTL (90 days retention)")
            except ClientError as e:
                print(f"Failed to enable TTL for traces table: {e}")

        # create spans table
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceInUseException':
            print(f"Table already exists: {traces_table}")
        else:
            print(f"Failed to create traces table: {e}")
            sys.exit(1)
    
    # create spans table
    try:
        print(f"\nCreating spans table: {spans_table}")

        spans = dynamodb.create_table(**get_create_table_kwargs(spans_table, SPANS_SCHEMA))

        if endpoint_url:
            spans.wait_until_exists()

        print(f"Created spans table: {spans_table}")

        # Enable TTL (AWS only)
        if not endpoint_url:
            try:
                client = boto3.client('dynamodb', region_name=region)
                client.update_time_to_live(
                    TableName=spans_table,
                    TimeToLiveSpecification=TTL_CONFIG
                )
                print("  Enabled TTL (90 days retention)")
            except ClientError as e:
                print(f"Failed to enable TTL for spans table: {e}")
    
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceInUseException':
            print(f"Table already exists: {spans_table}")
        else:
            print(f"Failed to create spans table: {e}")
            sys.exit(1)
    
    print("\n✅ DynamoDB tables created successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create DynamoDB tables for testing.')
    parser.add_argument(
        '--endpoint',
        default=None,
        help='DynamoDB endpoint URL (for local: http://localhost:8000)')
    parser.add_argument(
        '--region',
        default='eu-central-1',
        help='AWS region')
    parser.add_argument(
        '--traces-table',
        default='llm-tracer-dev-traces',
        help='Name of traces table')
    parser.add_argument(
        '--spans-table',
        default='llm-tracer-dev-spans',
        help='Name of spans table')

    args = parser.parse_args()
    
    create_tables(
        endpoint_url=args.endpoint,
        region=args.region,
        traces_table=args.traces_table,
        spans_table=args.spans_table,
    )
    