import rclpy
import zmq
import numpy as np
import cv2
import base64
import json
import time
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

class RosToZmqBridge(Node):
    def __init__(self):
        super().__init__('ros_to_zmq_bridge')
        self.bridge = CvBridge()
        self.frame_count = 0

        ctx = zmq.Context()
        self.socket = ctx.socket(zmq.PUB)
        self.socket.bind("tcp://*:5555")  # LeRobot ZMQCamera 默认端口

        self.get_logger().info('ROS到ZMQ桥接器已启动')
        self.get_logger().info('ZMQ发布地址: tcp://*:5555')
        
        self.create_subscription(
            Image,
            '/ascamera_hp60c/camera_publisher/rgb0/image',
            self.callback,
            10
        )
        self.get_logger().info('订阅话题: /ascamera_hp60c/camera_publisher/rgb0/image')

    def callback(self, msg):
        try:
            self.frame_count += 1
            
            # cvbridge转BGR（LeRobot期望的格式）
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # 编码为JPEG
            _, buf = cv2.imencode('.jpg', frame)
            jpeg_bytes = buf.tobytes()
            
            # 转换为base64
            jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')
            
            # 构造LeRobot期望的JSON格式
            current_time = time.time()
            json_data = {
                "timestamps": {"front_camera": current_time},
                "images": {"front_camera": jpeg_base64}
            }
            
            # 发送JSON字符串
            self.socket.send_string(json.dumps(json_data))
            
            # 每隔50帧输出一次信息
            if self.frame_count % 50 == 0:
                height, width = frame.shape[:2]
                self.get_logger().info(f'已发送 {self.frame_count} 帧, 图像尺寸: {width}x{height}, 数据大小: {len(jpeg_bytes)} 字节')
                
        except Exception as e:
            self.get_logger().error(f'处理图像时出错: {e}')

def main():
    rclpy.init()
    
    try:
        bridge = RosToZmqBridge()
        print("桥接器节点正在运行，按Ctrl+C停止...")
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        print("\n正在停止桥接器...")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        if 'bridge' in locals():
            bridge.destroy_node()
        try:
            rclpy.shutdown()
            print("桥接器已停止")
        except:
            pass
