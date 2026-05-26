import io

import boto3
from botocore.exceptions import ClientError


class S3Client:
    """Wrapper around boto3 S3 client providing upload, download, presigned URL, and delete."""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        bucket: str,
    ) -> None:
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        self.bucket = bucket

    def upload_file(self, key: str, data: bytes, content_type: str) -> str:
        """Upload bytes to S3 and return the s3://bucket/key URI."""
        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return f"s3://{self.bucket}/{key}"

    def download_file(self, key: str) -> bytes:
        """Download a file from S3 and return its raw bytes."""
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            raise FileNotFoundError(f"S3 object not found: s3://{self.bucket}/{key}") from exc

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for temporary object access."""
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_file(self, key: str) -> None:
        """Delete a file from S3."""
        self._s3.delete_object(Bucket=self.bucket, Key=key)


_s3_client: S3Client | None = None


def get_s3_client() -> S3Client:
    """Return a singleton S3Client configured from application settings."""
    global _s3_client
    if _s3_client is None:
        from src.config import get_settings

        settings = get_settings()
        _s3_client = S3Client(
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
            region=settings.aws_region,
            bucket=settings.aws_s3_bucket,
        )
    return _s3_client
