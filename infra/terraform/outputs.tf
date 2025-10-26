output "bucket_name" {
  value = aws_s3_bucket.sbuddy.bucket
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.sbuddy.domain_name
}

output "app_url" {
  value = "https://sbuddy.leitnersoft.com"
}

output "speech_api_url" {
  value = aws_apigatewayv2_stage.speech.invoke_url
}

output "speech_lambda_arn" {
  value = aws_lambda_function.speech.arn
}

output "exercise_completion_api_url" {
  value = "${trim(aws_apigatewayv2_stage.speech.invoke_url, "/")}/api/exercise-completions"
}
