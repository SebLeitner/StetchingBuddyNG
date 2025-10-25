terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "us-east-1" # CloudFront-Zertifikate erfordern us-east-1
}

resource "aws_s3_bucket" "sbuddy" {
  bucket = "sbuddy.leitnersoft.com"
}

resource "aws_s3_bucket_ownership_controls" "sbuddy" {
  bucket = aws_s3_bucket.sbuddy.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_public_access_block" "sbuddy" {
  bucket = aws_s3_bucket.sbuddy.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "sbuddy" {
  bucket = aws_s3_bucket.sbuddy.id
  index_document {
    suffix = "index.html"
  }
  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_policy" "sbuddy_public_read" {
  bucket = aws_s3_bucket.sbuddy.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = "*",
      Action    = ["s3:GetObject"],
      Resource  = "${aws_s3_bucket.sbuddy.arn}/*"
    }]
  })
}

data "aws_route53_zone" "zone" {
  name         = "leitnersoft.com"
  private_zone = false
}

resource "aws_acm_certificate" "cert" {
  domain_name       = "sbuddy.leitnersoft.com"
  validation_method = "DNS"
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
  zone_id = data.aws_route53_zone.zone.id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 300
}

resource "aws_acm_certificate_validation" "cert" {
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

resource "aws_cloudfront_distribution" "sbuddy" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Stretch Coach App"
  default_root_object = "index.html"
  aliases             = ["sbuddy.leitnersoft.com"]

  origin {
    domain_name = aws_s3_bucket_website_configuration.sbuddy.website_endpoint
    origin_id   = "s3-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3-origin"
    viewer_protocol_policy = "redirect-to-https"
    compress = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }

  viewer_certificate {
    acm_certificate_arn            = aws_acm_certificate_validation.cert.certificate_arn
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  price_class = "PriceClass_100"
}

resource "aws_route53_record" "sbuddy_alias" {
  zone_id = data.aws_route53_zone.zone.id
  name    = "sbuddy.leitnersoft.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.sbuddy.domain_name
    zone_id                = aws_cloudfront_distribution.sbuddy.hosted_zone_id
    evaluate_target_health = false
  }
}
