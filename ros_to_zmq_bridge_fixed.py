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
from threading import Lock

class RosToZmqBridge(Node):
    def __init__(self):
        super().__init__('ros_to_zmq_bridge')
        self.bridge = CvBridge()
        self.frame_count = 0
        self.data_lock = Lock()
        
        # 存储所有摄像头数据的字典
        self.camera_data = {}
        self.camera_timestamps = {}
        
        # 只保留RGB摄像头配置
        self.camera_configs = {
            '/ascamera_hp60c/camera_publisher/rgb0/image': 'front_camera',
            '/ascamera_hp60c/camera_publisher/rgb1/image': 'right_camera'
        }

        ctx = zmq.Context()
        self.socket = ctx.socket(zmq.PUB)
        self.socket.bind("tcp://*:5555")  # LeRobot ZMQCamera 默认端口

        self.get_logger().info('多摄像头ROS到ZMQ桥接器已启动')
        self.get_logger().info('ZMQ发布地址: tcp://*:5555')
        
        # 等待话题可用
        self.get_logger().info('等待话题可用...')
        time.sleep(2)  # 等待2秒让话题发布
        
        # 检查话题是否存在
        topic_names = self.get_topic_names_and_types()
        available_topics = [name for name, _ in topic_names]
        
        self.get_logger().info(f'可用话题: {available_topics}')
        
        # 为每个摄像头创建订阅
        for topic, camera_name in self.camera_configs.items():
            if topic in available_topics:
                self.get_logger().info(f'正在订阅话题: {topic} -> {camera_name}')
                self.create_subscription(
                    Image,
                    topic,
                    lambda msg, cam_name=camera_name, topic_name=topic: self.camera_callback(msg, cam_name, topic_name),
                    10
                )
                self.get_logger().info(f'订阅成功: {topic} -> {camera_name}')
            else:
                self.get_logger().warn(f'话题不存在: {topic}, 跳过 {camera_name}')
        
        # 启动发布线程
        self.publisher_thread = self.create_timer(0.033, self.publish_data)  # 约30fps
        self.get_logger().info('发布定时器已启动')

    def camera_callback(self, msg, camera_name, topic_name):
        """单个摄像头的回调函数"""
        try:
            # cvbridge转BGR（LeRobot期望的格式）
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # 编码为JPEG
            _, buf = cv2.imencode('.jpg', frame)
            jpeg_bytes = buf.tobytes()
            
            # 转换为base64
            jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')
            
            # 线程安全地更新数据
            with self.data_lock:
                self.camera_data[camera_name] = jpeg_base64
                self.camera_timestamps[camera_name] = time.time()
            
            self.frame_count += 1
            
            # 每隔100帧输出一次信息
            if self.frame_count % 100 == 0:
                height, width = frame.shape[:2]
                self.get_logger().info(f'{camera_name}: 已处理 {self.frame_count} 帧, 图像尺寸: {width}x{height}, 数据大小: {len(jpeg_bytes)} 字节')
                
        except Exception as e:
            self.get_logger().error(f'处理 {camera_name} 图像时出错: {e}')

    def publish_data(self):
        """发布所有摄像头数据"""
        try:
            with self.data_lock:
                if not self.camera_data:  # 如果没有数据，跳过
                    self.get_logger().warn('没有摄像头数据，跳过发布')
                    return
                
                # 构造LeRobot期望的JSON格式
                json_data = {
                    "timestamps": self.camera_timestamps.copy(),
                    "images": self.camera_data.copy()
                }
                
                # 发送JSON字符串
            self.socket.send_string(json.dumps(json_data))
            
            # 每隔100次发布输出一次状态信息
            if not hasattr(self, 'publish_count'):
                self.publish_count = 0
            self.publish_count += 1
            if self.publish_count % 100 == 0:
                self.get_logger().info(f'已发布 {self.publish_count} 次，当前摄像头数量: {len(self.camera_data)}')
            
        except Exception as e:
            self.get_logger().error(f'发布数据时出错: {e}')

def main():
    rclpy.init()
    
    try:
        bridge = RosToZmqBridge()
        print("多摄像头桥接器节点正在运行，按Ctrl+C停止...")
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
