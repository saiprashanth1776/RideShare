## RideShare Project
[Project Specifications](https://d1b10bmlvqabco.cloudfront.net/attach/k4vbpy4o35q1ci/jzb6kq5w25w4tm/k8py84sv1rlm/DBaaS__AMQP.pdf) 

#### Building on local machine
##### Instructions
- Start docker service
- Execute the setup script ```startup.sh```
    - Setup script builds and runs everything required. This will take a few minutes.
    - If you have no errors, RideShare is up and running!

Use the following Postman Collection to test the RideShare APIs,

[![Run in Postman](https://run.pstmn.io/button.svg)](https://app.getpostman.com/run-collection/c85f03faaffd465ae505)


##### Making changes 
If you make any changes, run ```startup.sh``` again to restart. (shutting down is not required.)

##### Shutting down
- The shutdown script stops all containers (+ it removes the temporary worker containers spawned during scaling)
      
##### Auto Scaling
The orchestrator keeps track of the number of read requests in every 2 min.
- 0 – 20 requests – 1 slave container is running
- 21 – 40 requests – 2 slave containers are running
- 41 – 60 requests – 3 slave containers are running

and so on.

To test this and make requests quickly, you can use the ```./dbaas/scale_up.sh``` script. This makes 21 async read calls.


##### Debug Issues
- If you face issues in the setup, try executing the commands in the ```startup.sh``` one by one manually
to identify the cause of the issue.
