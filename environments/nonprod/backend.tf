terraform {
  backend "s3" {
    # Supply the private backend values from an untracked backend configuration
    # file during local initialization. CI always uses -backend=false.
  }
}
