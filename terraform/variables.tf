variable "deploy_graphrag" {
  description = "Set to true to deploy the GraphRAG components (Redis, Pub/Sub, etc.)"
  type        = bool
}

variable "gcp_region" {
  description = "The Google Cloud region where resources will be deployed."
  type        = string
}

variable "project_id" {
  description = "The Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "The Google Cloud region where resources will be deployed."
  type        = string
}

variable "location" {
  description = "The Google Cloud location for resources."
  type        = string
}

variable "repository_id" {
  description = "The ID of the Docker repository."
  type        = string
}

variable "image_name" {
  description = "The name of the Docker image."
  type        = string
}

variable "image_url" {
  description = "The URL of the Docker image."
  type        = string
}

variable "query_engine_sa_email" {
  description = "The email of the query-engine service account."
  type        = string
}

variable "memgraph_host" {
  description = "Memgraph host for the query engine."
  type        = string
}

variable "memgraph_port" {
  description = "Memgraph port for the query engine."
  type        = number
}

variable "memgraph_user" {
  description = "Memgraph username for the query engine."
  type        = string
}

variable "memgraph_password" {
  description = "Memgraph password for the query engine."
  type        = string
  sensitive   = true
}

variable "vpc_connector" {
  description = "The ID of the VPC Access connector."
  type        = string
}

variable "image_tag" {
  description = "The tag for the docker image"
  type        = string
  default = "latest"
}

variable "docker_registry_location" {
  description = "The location of the Docker registry."
  type        = string
}