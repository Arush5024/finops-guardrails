# PLAN-ONLY FIXTURE. Never apply this.
#
# A deliberately wasteful stack used to demonstrate what CostGuard catches.
# The provider uses mock credentials and skips all AWS API calls, so
# `terraform plan` works with no AWS account and costs nothing.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region     = "ap-south-1"
  access_key = "mock"
  secret_key = "mock"

  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

locals {
  placeholder_ami = "ami-00000000000000000"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.0.0/24"
}

resource "aws_subnet" "private" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
}

resource "aws_eip" "nat" {
  domain = "vpc"
}

# Always-on NAT gateway for a single dev instance.
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id
}

# Oversized, untagged, on gp2.
resource "aws_instance" "app" {
  ami           = local.placeholder_ami
  instance_type = "m5.2xlarge"
  subnet_id     = aws_subnet.private.id

  root_block_device {
    volume_type = "gp2"
    volume_size = 200
  }
}

# A large gp2 volume attached to nothing.
resource "aws_ebs_volume" "scratch" {
  availability_zone = "ap-south-1a"
  type              = "gp2"
  size              = 1000
}

# Multi-AZ database for a dev workload.
resource "aws_db_instance" "main" {
  identifier          = "wasteful-dev"
  engine              = "postgres"
  instance_class      = "db.m5.large"
  allocated_storage   = 100
  storage_type        = "gp2"
  multi_az            = true
  username            = "app"
  password            = "plan-only-fixture"
  skip_final_snapshot = true

  tags = {
    Environment = "dev"
  }
}

# Logs kept forever.
resource "aws_cloudwatch_log_group" "app" {
  name = "/wasteful/app"
}
