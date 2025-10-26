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

data "archive_file" "polly_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda"
  output_path = "${path.module}/build/polly_lambda.zip"
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

resource "aws_iam_role" "speech_lambda" {
  name               = "stretch-coach-speech-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "speech_lambda_basic_execution" {
  role       = aws_iam_role.speech_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "speech_lambda_custom" {
  name = "stretch-coach-speech-lambda-policy"
  role = aws_iam_role.speech_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "polly:SynthesizeSpeech",
          "polly:StartSpeechSynthesisTask"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "speech_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.speech.function_name}"
  retention_in_days = 14

  depends_on = [aws_lambda_function.speech]
}

resource "aws_lambda_function" "speech" {
  function_name = "stretch-coach-speech"
  role          = aws_iam_role.speech_lambda.arn
  handler       = "polly_handler.lambda_handler"
  runtime       = "python3.10"
  filename      = data.archive_file.polly_lambda.output_path
  source_code_hash = data.archive_file.polly_lambda.output_base64sha256
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      DEFAULT_LANGUAGE   = "de-DE"
      DEFAULT_VOICE      = "Vicki"
      MAX_TEXT_LENGTH    = "1500"
      CORS_ALLOW_ORIGIN  = "https://sbuddy.leitnersoft.com"
    }
  }
}

resource "aws_apigatewayv2_api" "speech" {
  name          = "stretch-coach-speech-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["Content-Type", "Authorization"]
    allow_methods     = ["OPTIONS", "POST"]
    allow_origins     = ["https://sbuddy.leitnersoft.com"]
    max_age           = 3600
  }
}

resource "aws_apigatewayv2_integration" "speech" {
  api_id                 = aws_apigatewayv2_api.speech.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.speech.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "speech" {
  api_id    = aws_apigatewayv2_api.speech.id
  route_key = "POST /api/speak"
  target    = "integrations/${aws_apigatewayv2_integration.speech.id}"
}

resource "aws_apigatewayv2_stage" "speech" {
  api_id      = aws_apigatewayv2_api.speech.id
  name        = "$default"
  auto_deploy = true

  depends_on = [aws_apigatewayv2_route.speech]
}

resource "aws_lambda_permission" "speech_apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.speech.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.speech.execution_arn}/*/*"
}
