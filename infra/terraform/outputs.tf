output "bucket_name" {
  value = aws_s3_bucket.sbuddy.bucket
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.sbuddy.domain_name
}

output "app_url" {
  value = "https://sbuddy.leitnersoft.com"
}
