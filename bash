lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=yao_follower_arm \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=yao_leader_arm
    
    
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=yao_follower_arm \
    --robot.cameras="{ front: {type: zmq, server_address: "localhost", port: 5555, camera_name: "front_camera"}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=yao_leader_arm \
    --display_data=true
    
    
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=yao_follower_arm \
    --robot.cameras="{ front: {type: zmq, server_address: \"localhost\", port: 5555, camera_name: \"front_camera\", width: 640, height: 480, fps: 30}, right: {type: zmq, server_address: \"localhost\", port: 5555, camera_name: \"right_camera\", width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=yao_leader_arm \
    --display_data=true
