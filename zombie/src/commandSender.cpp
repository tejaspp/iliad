/*
 * 
 * Based on commandSender from orunav_mpc
 * 
 * Uses different constructors for simulated and real robot, not compilation.
 * It is decoupled from thread data model.
 * 
 * 
 * */



#include "commandSender.h"


/**
 * @brief Constructor
 *
 * @param[in,out] thread_data thread data.
 */
 
 
 
commandSender::commandSender(double _max_car_velocity_change, double _max_car_steer_angle_change) 
{
   	pdoCounter = 0;

	// clear timeout errors in plc
	// this is important!
	for(unsigned int i = 0; i < SW_CAN_CLEAR_ITER_NUM; ++i)
	{
		formWriteMSG (0, 0, 0);
		usleep(SW_CAN_CLEAR_DELAY);
	}

	message_flags = SW_CAN_FLAG_OVERRIDE | SW_CAN_FLAG_DRIVE_ON | SW_CAN_FLAG_STEER_ON;
	//message_flags = SW_CAN_FLAG_OVERRIDE;
	

}





/**
 * @brief Forms and sends a CAN message containing command (is not used in simulation).
 *
 * @param[in] speed speed (mm/s)
 * @param[in] angle angle (centidegree)
 * @param[in] flags flags for the controller (not for canlib)
 */
void commandSender::formWriteMSG(int speed, int angle, const char flags)
{
    canMessage msg;

    msg.flag = 0;
    msg.dlc = 8;
    msg.time_stamp = 0;
    msg.id = SW_CAN_COMMAND_ID + SW_CAN_NODE_ID;


    msg.msg[0] = speed & 0xff;
    msg.msg[1] = speed >> 8 & 0xff;
    msg.msg[2] = angle & 0xff;
    msg.msg[3] = angle >> 8 & 0xff;

    msg.msg[4] = pdoCounter;
    ++pdoCounter;

    msg.msg[5] = flags;

    msg.msg[6] = 0;
    msg.msg[7] = 0;


    sw_can.canWrite(msg);
}



/**
 * @brief Forms and sends a CAN message containing command (is not used in simulation).
 *
 * @param[in] speed speed (mm/s)
 * @param[in] angle angle (centidegree)
 */
void commandSender::formWriteMSG(int speed, int angle)
{
     formWriteMSG( speed,  angle, message_flags);
}
