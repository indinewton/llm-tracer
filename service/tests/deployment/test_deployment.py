"""
Depyloment smoke tests for verifying live infra.

These tests are lightweigth and designed to run against deployed environments.
test if:
 - Api health is responfing
 - DynamoDB tables exists and are accessible
 - Basic trace creation works end-to-end
 - table indexes are operational.

"""

import pytest
import boto3
from datetime import datetime, UTC


class TestAPIHealth:
    """Test 1: verifiy API is healthy"""

    def test_health_endpoint(self, http_client, deployment_config):
        """Test health endpoint"""
        response = http_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["storage"] is not None


class TestDynamoDBTables:
    """Test 2: verify dynamoDB tables exist and are operational."""

    def test_tables(self, dynamodb_client, deployment_config):
        """Test dynamoDB tables"""
        tables = [
            deployment_config["traces_table"],
            deployment_config["spans_table"],
        ]

        for table_name in tables:
            response = dynamodb_client.describe_table(TableName=table_name)
            table  = response["Table"]
            
            assert table["TableStatus"] == "ACTIVE", f"Table {table_name} is not active"

            # Verify GSI exists and is active
            gsi_list = table.get("GlobalSecondaryIndexes", [])

            assert len(gsi_list) > 0, f"GSI not found for table {table_name}"
            
            for gsi in gsi_list:
                assert gsi["IndexStatus"] == "ACTIVE", (
                    f"GSI {gsi['IndexName']} on {table_name} is not active"
                )


class TestBasicTraceWorkflow:
    """Test 3: verify basic trace workflow"""

    def test_trace_workflow(self, http_client, deployment_config):
        """Test basic trace workflow"""
        
        def test_create_and_fetch_trace(self, http_client, deployment_config):
            """Test create and fetch trace"""
            # Create a trace
            trace_data = {
                "name": f"Deployment-test-{datetime.now(UTC).isoformat()}",
                "project_id": deployment_config["api_key"].replace("project-", "", 1),
                "metadata": {"test": True, "environment": deployment_config["environment"]},
                "tags": ["deployment-test", "automated"],
            }

            create_response = http_client.post("/api/traces", json=trace_data)
            assert create_response.status_code == 200, (
                f"Failed to create trace: {create_response.text}"
            )
            
            result = create_response.json()
            assert result["status"] == "created"
            
            trace_id = result["trace_id"]

            # Fetch trace
            get_response = http_client.get(f"/api/traces/{trace_id}")
            assert get_response.status_code == 200, (
                f"Failed to fetch trace: {get_response.text}"
            )

            trace = get_response.json()
            assert trace["trace"]["trace_id"] == trace_id
            assert trace["trace"]["name"] == trace_data["name"]

            # Complete trace (cleanup)
            complete_response = http_client.patch(
                f"/api/traces/{trace_id}/complete",
                json={"output": "Deployment test completed successfully"})
            
            assert complete_response.status_code == 200, (
                f"Failed to complete trace: {complete_response.text}"
            )


class TestDynamoDBIndexQuery:
    """Test 4: verify dynamoDB index query"""

    def test_project_time_index_query(self, dynamodb_client, deployment_config):
        """Test project time index query"""
        from boto3.dynamodb.conditions import Key
        
        dynamodb = boto3.resource(
            "dynamodb",
            region_name=deployment_config["aws_region"]
        )
        traces_table = dynamodb.Table(deployment_config["traces_table"])
        
        # Extract project_id from api_key
        project_id = deployment_config["api_key"].replace("project-", "", 1)

        # Query using GSI - this verifies the index is operational
        response = traces_table.query(
            IndexName="project-time-index",
            KeyConditionExpression=Key("project_id").eq(project_id),
            Limit=1,
            ScanIndexForward=False,  # Newest first
        )

        # We don't assert on count (might be 0 in freshg env)
        # Just verif the query executed successfully
        assert "Items" in response
        assert "Count" in response
        assert response["Count"] >= 0

        # Also verify we can query the spans table GSI
        spans_table = dynamodb.Table(deployment_config["spans_table"])

        # Use a dummy trace_id - we just want to verify if index is operational
        span_response = spans_table.query(
            IndexName="trace-index",
            KeyConditionExpression=Key("trace_id").eq("dummy_trace_id"),
            Limit=1,
        )
        assert "Items" in span_response
