# PLAN-ONLY FIXTURE.
#
# The same workload as wasteful-stack, built the way CostGuard wants it.
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

  default_tags {
    tags = {
      Owner       = "arush"
      Environment = "dev"
      CostCenter  = "demo"
    }
  }
}

locals {
  placeholder_ami = "ami-00000000000000000"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

# A public subnet avoids the NAT gateway for a single dev instance.
resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.0.0/24"
}

resource "aws_instance" "app" {
  ami           = local.placeholder_ami
  instance_type = "t4g.small"
  subnet_id     = aws_subnet.public.id

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
  }
}

resource "aws_db_instance" "main" {
  identifier          = "compliant-dev"
  engine              = "postgres"
  instance_class      = "db.t4g.micro"
  allocated_storage   = 20
  storage_type        = "gp3"
  multi_az            = false
  username            = "app"
  password            = "plan-only-fixture"
  skip_final_snapshot = true
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/compliant/app"
  retention_in_days = 14
}
