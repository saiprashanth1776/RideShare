## Load Balancing for RideShare
[Assignment Specifications](https://d1b10bmlvqabco.cloudfront.net/attach/k4vbpy4o35q1ci/jzb6kq5w25w4tm/k7evdrlwudxl/Assignment_3.pdf) 
#### Instructions
- Make Two Seperate AWS Instances
- Install Docker & Docker Compose (Docker Desktop includes Docker Compose) on both.
- Copy one folder to each instance. 
- Run ```docker-compose up --build```
- Setup target groups and load balancer in AWS


#### Testing
### Public IPs & DNS
###### (When instances are active)
- Users Instance : http://52.73.112.73
- Rides Instance : http://18.211.40.79
- Load Balancer DNS: http://rideshare-load-balancer-947103600.us-east-1.elb.amazonaws.com




