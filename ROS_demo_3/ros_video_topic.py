###!/usr/bin/env python

import rospy
from sensor_msgs.msg import Image
import sys
#sys.path.append('/data/grebici/catkin_WBC/src/my_pkgs/custom_msg')
from custom_msg.msg import Frame_info
from geometry_msgs.msg import Point
import numpy as np
import pyrealsense2 as rs

import time

import mediapipe as mp
import cv2

def get_hand_coordinates(pose_landmarks):
    left_hand_coords = {"max_x": -1000, "max_y": -1000, "min_x": 1000, "min_y": 1000}
    right_hand_coords = {"max_x": -1000, "max_y": -1000, "min_x": 1000, "min_y": 1000}

    left_hand_index = [17, 19, 21] # pinky index thumb
    right_hand_index = [18, 20, 22]

    # Extract the coordinates of the left and right hands
    for idx, landmark in enumerate(pose_landmarks.landmark):
        if idx in left_hand_index:
              # Left hand
            if landmark.x > left_hand_coords["max_x"]:
                left_hand_coords["max_x"] = landmark.x
            if landmark.y > left_hand_coords["max_y"]:
                left_hand_coords["max_y"] = landmark.y
            if landmark.x < left_hand_coords["min_x"]:
                left_hand_coords["min_x"] = landmark.x
            if landmark.y < left_hand_coords["min_y"]:
                left_hand_coords["min_y"] = landmark.y

        elif idx in right_hand_index:  # Right hand

            if landmark.x > right_hand_coords["max_x"]:
                right_hand_coords["max_x"] = landmark.x
            if landmark.y > right_hand_coords["max_y"]:
                right_hand_coords["max_y"] = landmark.y
            if landmark.x < right_hand_coords["min_x"]:
                right_hand_coords["min_x"] = landmark.x
            if landmark.y < right_hand_coords["min_y"]:
                right_hand_coords["min_y"] = landmark.y


    if any(item < 0 or item > 1 for item in left_hand_coords.values()): # coordinates are out of the frame
        left_hand_coords = None
    if any(item <0 or item > 1 for item in right_hand_coords.values()):
        right_hand_coords = None

    return right_hand_coords, left_hand_coords # we have to switch them here due to the cv2.flip

def crop_hand(frame, hand_coords):
    # image_height, image_width = frame.height, frame.width
    
    image_height, image_width, _ = frame.shape

    margin = 80

    x_min = max(0, int(hand_coords["min_x"] * image_width) - margin)
    y_min = max(0, int(hand_coords["min_y"] * image_height) - margin)
    x_max = min(image_width - 1, int(hand_coords["max_x"] * image_width) + margin)
    y_max = min(image_height - 1, int(hand_coords["max_y"] * image_height) + margin)

    # Crop the image around the hand region
    hand_image = frame[y_min:y_max, x_min:x_max]

    return hand_image

def classify_hand(mp_image):

        # mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data = hand_image)
        # mp_image = hand_image
        result = recognizer.recognize(mp_image) 
    
        try:
            prediction = result.gestures[0][0].category_name
            confidence = result.gestures[0][0].score          
        except:
            prediction = "no hands hee"
            confidence = ""

        return prediction, confidence



if __name__ == '__main__':
    ### CONSTANTS ###
    DETECTION = True
    DISPLAY = False
    
    ### END CONSTANTS ###
    
    # initialize the node
    rospy.init_node('keypoints_detector_node')

    # Create a publisher for the keypoints array
    keypoints_pub = rospy.Publisher('video_info_topic', Frame_info, queue_size=10)

    # create the mediapipe tools for pose estimation and landmark drawing
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    # create the options for configutation of the hand gesture revognizer
    BaseOptions = mp.tasks.BaseOptions
    GestureRecognizer = mp.tasks.vision.GestureRecognizer
    GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    # Create a gesture recognizer instance with the image mode:
    options = GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path='hand_recognition_model/gesture_recognizer.task'),
        running_mode=VisionRunningMode.IMAGE,
        num_hands = 1,
        min_hand_detection_confidence=0.2,
        min_hand_presence_confidence=0.2)
    
    # create the cv2 window
    if DISPLAY:
        cv2.namedWindow('Webcam Feed', cv2.WINDOW_NORMAL)

    # Configure the RealSense pipeline
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1280, 800, rs.format.bgr8, 30)
    
    # Initialize the RealSense pipeline
    cfg = pipeline.start(config)

    try:
        with GestureRecognizer.create_from_options(options) as recognizer:
            with mp_pose.Pose(
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5) as pose:    
                while True:

                    frames = pipeline.wait_for_frames()
                    color_frame = frames.get_color_frame()
                    
                    if not color_frame:
                        continue

                    color_image = np.asarray(color_frame.get_data())
                    frame = cv2.flip(color_image,1)

                    pose_results = pose.process(frame) # find body keypoints

                    right_pred = "no hands"
                    right_conf = ""

                    if pose_results.pose_landmarks:
                        # Get the coordinates of the right hand
                        _, right_hand_coords = get_hand_coordinates(pose_results.pose_landmarks)
                        
                        if right_hand_coords is not None:
                            right_hand_image = (crop_hand(frame, right_hand_coords))
                            right_hand_image = cv2.cvtColor(right_hand_image, cv2.COLOR_BGR2RGB)
                            right_hand_image = mp.Image(image_format=mp.ImageFormat.SRGB, data = right_hand_image)
                            #hands detection and classification
                            right_pred, right_conf = classify_hand(right_hand_image)
                            
                            if DISPLAY:
                                # Draw the bounding box and prediction on the frame
                                margin_x = 80
                                margin_y = int(margin_x * 1.25)
                                image_height, image_width, _ = frame.shape
                                x_min = max(0, int(right_hand_coords["min_x"] * image_width) - margin_x)
                                y_min = max(0, int(right_hand_coords["min_y"] * image_height) - margin_y)
                                x_max = min(image_width - 1, int(right_hand_coords["max_x"] * image_width) + margin_x)
                                y_max = min(image_height - 1, int(right_hand_coords["max_y"] * image_height) + margin_y)
                                start_box = (x_min, y_min)
                                end_box = (x_max, y_max)
                                frame = cv2.rectangle(frame, start_box, end_box, (255,0,0), 2)
                                cv2.putText(frame, right_pred, start_box, cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

                    new_frame_time = time.time()
                    fps = 1/(new_frame_time-prev_frame_time)
                    prev_frame_time = new_frame_time
                    
                    if DISPLAY:
                    
                        # annotated_image = draw_landmarks_on_image(frame, result)
                        annotated_image = frame

                        mp_drawing.draw_landmarks(
                        annotated_image,
                        pose_results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS,
                        landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style())
                        
                        # Write fps on the frame
                        cv2.putText(annotated_image, f"FPS: {fps}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        
                        # Display the frame in a window named 'Webcam Feed'
                        cv2.imshow('Webcam Feed', annotated_image)
                
                    ### NEED TO CONFIGURE THE MESSAGE
                    keypoints_pub.publish(message)
    except KeyboardInterrupt:
        pipeline.stop()
        cv2.destroyAllWindows()
        print("STOPPEDDDDDDD")
    

    
    
   