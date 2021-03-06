#!/usr/bin/env python

'''
Like velParser but decouples incoming command from applied command.
Why? Because a single Vtrans,Vrot can mean different Vm,Omega depending on the
current wheel orientation .


Reads a Twist containing translational vel and rotational vel and casts to another where we have
motor wheel linear velocity and turning speed (tricycle model)

It was 'very' loosely inspired by:
http://wiki.ros.org/teb_local_planner/Tutorials/Planning%20for%20car-like%20robots

'''

import tf
import rospy
import math
from geometry_msgs.msg import Twist, PoseStamped
from tf.transformations import euler_from_quaternion


import rospy


class vParser():

    def waitForTopic(self, topicFullName):
        isRunning = False

        while (not isRunning):
            currentTopics = rospy.get_published_topics()
            # flatten them
            currentTopics = [item for sublist in currentTopics for item in sublist]
            #print currentTopics
            isRunning = (topicFullName in currentTopics) or ('/'+topicFullName in currentTopics)
            if not isRunning:
                rospy.loginfo('Topic '+topicFullName+' not found. Waiting 2 secs ...')
                rospy.sleep(2.)
        return

    # Must have __init__(self) function for a class, similar to a C++ class constructor.
    def __init__(self):

        # ................................................................
        # read ros parameters
        self.loadROSParams()
        # ................................................................
        # Other config params
        self.rel_yaw = 0.0
        # when casting angle increment to rot speed, use this factor (Hz.)
        self.omegaFreq = 20.0
        self.publishTime = 1.0/self.omegaFreq
        self.watchdogTime = 0.1
        # ................................................................
        # initial state
        self.v = 0
        self.omega = 0
        self.watchdogTimer = rospy.Timer(rospy.Duration(
            self.watchdogTime), self.stopRobot, oneshot=True)

        # start ros subs/pubs/servs....
        self.initROS()

        rospy.loginfo("Node 'vel_parser' started.\nListening to %s, publishing to %s.",
                      self.in_cmd_topic, self.out_cmd_topic)
        self.periodicPublish(None)
        rospy.spin()

    def loadROSParams(self):
        # distance between back wheels axis and front motor wheel. meters
        self.wheelsAxesDist = rospy.get_param('~wheelsAxesDist', 1.2)

        # max angle of the turning wheel before considering turning in place. in radians
        self.inPlacePhi = rospy.get_param('~inPlacePhi', 1.57)  # (~89.95 degs)

        # max angle tolerance for the turning wheel. in radians
        self.phiTol = rospy.get_param('~phiTol', 0.1)  # (~0.57 degs)

        # use steering wheel speeds instead of angles.
        self.useOmega = rospy.get_param('~useOmega', True)

        # allow motor wheel to move while being reoriented
        self.moveWhileOrienting = rospy.get_param('~moveWhileOrienting', True)

        # More convenient ...
        self.minCosP = math.cos(self.inPlacePhi)

        self.in_cmd_topic = rospy.get_param('~in_cmd_topic', '/robot2/move_base/cmd_vel')
        self.out_cmd_topic = rospy.get_param('~out_cmd_topic', '/robot2/controller/cmd_vel')
        self.steer_pose_cmd_topic = rospy.get_param('~steer_pose_cmd_topic', '/robot2/steer_pose')

    def initROS(self):
        self.waitForTopic(self.steer_pose_cmd_topic)
        rospy.Subscriber(self.steer_pose_cmd_topic, PoseStamped,
                         self.steer_pose_callback, queue_size=1)
        self.waitForTopic(self.in_cmd_topic)
        rospy.Subscriber(self.in_cmd_topic, Twist, self.cmd_callback, queue_size=1)
        self.pub = rospy.Publisher(self.out_cmd_topic, Twist, queue_size=1)

    def velsToMotrix(self, vtrans, vrot, axesDist):

        phi = math.atan2(axesDist * vrot, vtrans)

        if phi > math.pi/2.0:
            phi = phi - (math.pi)
        elif phi < -math.pi/2.0:
            phi = phi + math.pi

        cosP = math.cos(phi)
        if abs(cosP) > self.minCosP:
            vm = vtrans/math.cos(phi)
        else:
            # when turning in place, we can use this relation between speeds, as vtrans == 0
            vm = abs(vrot) * axesDist
            rospy.logdebug('Big turning angle ({0}), turning in place vm: ({1})'.format(
                phi*180.0/math.pi, vm))

        return (vm, phi)

    def wrapAngle(self, a):
        phase = (a + math.pi) % (2 * math.pi) - math.pi
        return phase

    def getYaw(self):
        return self.rel_yaw

    def cmd_callback(self, data):
        # what I get from the incoming data
        self.v = data.linear.x
        self.omega = data.angular.z
        rospy.logdebug('Received (vtrans, vrot): ({0},{1})'.format(self.v, self.omega))
        self.watchdogTimer.shutdown()
        self.watchdogTimer = rospy.Timer(rospy.Duration(
            self.watchdogTime), self.stopRobot, oneshot=True)

    def stopRobot(self, evt):
        self.v = 0
        self.omega = 0

    def publish_speeds(self):
        msg = Twist()

        # if received 0,0 just stop. don't mind aligning the wheel...
        if (self.v == self.omega == 0.0):
            msg.linear.x = 0.0
            msg.angular.z = 0.0
            self.pub.publish(msg)
            return

        # equivalence to motor wheel speed and steering wheel angle.
        (v_m, des_y) = self.velsToMotrix(self.v, self.omega, self.wheelsAxesDist)

        # GAZEBO UNDERSTANDS SPEEDS, NOT ANGLES. DO CONVERSION IF DEMANDED
        if self.useOmega:
            angDiff = self.wrapAngle(des_y - self.getYaw())
            if abs(angDiff) < self.phiTol:
                angDiff = 0
            omega_m = 0.21 * angDiff / self.publishTime
        else:
            omega_m = des_y

        if self.useOmega:
            rospy.logdebug('Equals to (v_motrix, omega): ({0},{1})'.format(v_m, omega_m))
        else:
            rospy.logdebug('Equals to (v_motrix, yaw): ({0},{1})'.format(v_m, omega_m))

        msg.linear.x = v_m
        msg.angular.z = omega_m
        self.pub.publish(msg)
        rospy.logdebug('Sended (v_m,omega_m): ({0},{1})'.format(
            msg.linear.x, msg.angular.z))

    def prev_cmd_callback(self, data):
        msg = Twist()

        # what I get from the incoming data
        v = data.linear.x
        omega = data.angular.z

        rospy.logdebug('Received (v,omega): ({0},{1})'.format(v, omega))

        # if received 0,0 just stop. don't mind aligning the wheel...
        if (v == omega == 0.0):
            msg.linear.x = 0.0
            msg.angular.z = 0.0
            self.pub.publish(msg)
            return

        # equivalence to motor wheel speed and steering wheel angle.
        (v_m, des_y) = self.velsToMotrix(v, omega, self.wheelsAxesDist)

        rospy.logdebug('Equals to (v_m,des_y): ({0},{1})'.format(v_m, des_y))
        rospy.logdebug('Current (yaw): ({0})'.format(self.getYaw()))

        # achieve command in two steps:
        # first step: turn motor wheel in place until we achieve desired orientation
        if self.moveWhileOrienting:
            msg.linear.x = v_m
        else:
            msg.linear.x = 0

        angDiffPrev = math.pi/2.0
        hasTurned = False
        while (not hasTurned):
            angDiff = self.wrapAngle(des_y - self.getYaw())

            # avoid multiple useless sendings
            if angDiff != angDiffPrev:

                # GAZEBO UNDERSTANDS SPEEDS, NOT ANGLES. DO CONVERSION IF DEMANDED
                if self.useOmega:
                    omega_m = angDiff * self.omegaFreq
                else:
                    omega_m = des_y
                    angDiff = 0  # we set the desired angle once
                msg.angular.z = omega_m

                self.pub.publish(msg)
                hasTurned = abs(angDiff) < self.phiTol
                rospy.logdebug('Angle diff ({2}).Sending (v_m,omega_m): ({0},{1})'.format(
                    msg.linear.x, msg.angular.z, angDiff))
                angDiffPrev = angDiff

        # second step: stop turning motor wheel and move it as demanded
        msg.linear.x = v_m

        # GAZEBO UNDERSTANDS SPEEDS, NOT ANGLES. DO CONVERSION IF DEMANDED
        if self.useOmega:
            omega_m = 0
        else:
            omega_m = des_y
        msg.angular.z = omega_m

        self.pub.publish(msg)
        rospy.logdebug('Achieved final angle ({2}).Sending (v_m,omega_m): ({0},{1})'.format(
            msg.linear.x, msg.angular.z, self.getYaw()))

    def steer_pose_callback(self, msg):
        q = [msg.pose.orientation.x, msg.pose.orientation.y,
             msg.pose.orientation.z, msg.pose.orientation.w]
        (roll, pitch, yaw) = euler_from_quaternion(q)
        self.rel_yaw = yaw

    def periodicPublish(self, evt):
        self.publish_speeds()
        rospy.logdebug("Next udpate in:"+str(self.publishTime))
        rospy.Timer(rospy.Duration(self.publishTime), self.periodicPublish, oneshot=True)


# Main function.
if __name__ == '__main__':
    rospy.init_node('velocityParser_node')  # , log_level=rospy.DEBUG)
    # Go to class functions that do all the heavy lifting. Do error checking.
    try:
        goGo = vParser()
    except rospy.ROSInterruptException:
        pass
