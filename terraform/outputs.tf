output "query_engine_service_url" {
  description = "The URL of the deployed query-engine Cloud Run service."
  value       = google_cloud_run_v2_service.query_engine_fn[0].uri
}