"""AWS lambda handler for FastAPI application"""

from mangum import Mangum
from src.server import app

# Wrap fastAPI app for lambda
# lifespan="off" prevents startup/shutdown events from blocking
handler = Mangum(app, lifespan="off")
