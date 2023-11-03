import tkinter
from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
import tkinter.messagebox
import customtkinter
import subprocess
import pyuac
import paho.mqtt.client as mqtt
import cantools
from PIL import Image, ImageTk
import time
import os
import sys


#define global variable for the state of the MQTT connection
global MQTT_Connection_state
global dbc_messages
dbc_messages = []
global id_indexes
# create an MQTT client object
client = mqtt.Client()

MQTT_Connection_state = False

#Decode CAN Frames in MQTT RT messages
def frames_received(msg_received):

    # #-------------------------------test------------------------------------------------
    # self.i = self.i%255 + 1
    # msg_received = [5, 100, 0, 120, 226, 0,
    #         0, 0, 1, 244, 4, 0, 128, 170, 18, 21, 72, 132, 18, 21, 84, 1,
    #         0, 0, 3, 61, 2, 0, 129, 101, 102, 103, 104, 105, 106, 107, 108, 2,
    #         0, 0, 3, 62, 3, 0, 128, 201, 202, 203, 204, 205, 206, 207, 208, 3,
    #         0, 0, 3, 61, 5, 0, 128, 101, 102, 103, 104, 105, 106, 107, 108, 2,
    #         0, 0, 3, 61, 1, 0, 129, 101, 102, 103, 104, 105, 106, 107, 108, 2,]
    # # #-----------------------------------------------------------------------------------

    #nb trame
    nb_trames = msg_received[0]

    #get compteur signal triangle
    compteur = msg_received[5]

    #get can data (id, dlc et data)
    for i in range(0,nb_trames) :
        
        #Récupère data pour chaque frame
        frame_id  = msg_received[6+(i*16)] << 24 | msg_received[7+(i*16)] << 16 | msg_received[8+(i*16)] << 8 | msg_received[9+(i*16)]
        frame_dlc = msg_received[12+i*16] >> 4
        frame_ext = msg_received[12+i*16] & 0xF
        frame_data = msg_received[13+(i*16):20+(i*16)+1]

        reception_time = time.perf_counter()  # get the reception time in seconds

        # find the dictionary with the frame ID
        for i, dict in enumerate(dbc_messages):
            if dict['id'] == frame_id:
                prev_timestamp = dict['prev_timestamp'] #Get previous timestamp of the CAN frame
                dbc_messages[i]['prev_timestamp'] = reception_time   #Update the previous timestamp in the list of messages
                break

        
        frame_cycle_time = int(round((reception_time - prev_timestamp) * 1000))

        #Update the display
        text = app.can_frames_tr_frame.get("1.0", "end")
        
        #Split text into lines
        lines = text.splitlines()

        line_to_update = 0
        #Find the index of the line to update (if it exists)
        for i, ligne in enumerate(lines[3:]) :
            if(ligne[2:9] != "") :
                if int(ligne[2:9], 16) == frame_id :
                    line_to_update = i + 3
                    break

        if(line_to_update != 0) : #Found frame to update
            
            #Check checkboxes for things to update
            if(app.payload_checkbox_var.get() == "on" and app.cycle_time_checkbox_var.get() == "on") :
                lines[line_to_update] = lines[line_to_update][:28] + "  " * 8 +"{}".format(' '.join([hex(i)[2:].zfill(2) for i in frame_data]).upper())  + "  " * 9 + "{} ms".format(frame_cycle_time)
            elif(app.payload_checkbox_var.get() == "on" and app.cycle_time_checkbox_var.get() == "off") :
                lines[line_to_update] = lines[line_to_update][:28] + "  " * 8 +"{}".format(' '.join([hex(i)[2:].zfill(2) for i in frame_data]).upper())  
            elif(app.payload_checkbox_var.get() == "off" and app.cycle_time_checkbox_var.get() == "on") :
                lines[line_to_update] = lines[line_to_update][:28] + "  " * 8 + " " * 44 + "  " * 9 + "{} ms".format(frame_cycle_time)
            else :
                lines[line_to_update] = lines[line_to_update][:28]
            

            # Join the remaining lines back together into a single string
            updated_text = '\n'.join(lines)

            # Delete the current contents of the textbox and insert the updated text
            app.can_frames_tr_frame.configure(state='normal')
            app.can_frames_tr_frame.delete("1.0", "end")
            app.can_frames_tr_frame.insert("1.0", updated_text)
            app.can_frames_tr_frame.configure(state='disabled')




def parse_dbc_file(filename):
    db = cantools.database.load_file(filename)

    global dbc_messages 
    dbc_messages = []

    for message in db.messages:
        message_dict = {}
        message_dict['name'] = message.name
        message_dict['dlc'] = message.length
        message_dict['id'] = message.frame_id
        message_dict['signals'] = []
        message_dict['prev_timestamp'] = 0.0

        for signal in message.signals:
            signal_dict = {}
            signal_dict['name'] = signal.name
            signal_dict['start_bit'] = signal.start
            signal_dict['length'] = signal.length
            signal_dict['endianess'] = signal.byte_order
            signal_dict['is_signed'] = signal.is_signed
            signal_dict['scale'] = signal.scale
            signal_dict['offset'] = signal.offset
            signal_dict['minimum'] = signal.minimum
            signal_dict['maximum'] = signal.maximum
            signal_dict['unit'] = signal.unit
            message_dict['signals'].append(signal_dict)

        dbc_messages.append(message_dict)

# define a function to add the blinking effect to the whole text
def blink_all():
    app.textbox.tag_remove("highlight", "1.0", END)
    app.textbox.tag_add("highlight", "1.0", END)
    app.textbox.tag_config("highlight", background="grey")
    app.textbox.after(100, remove_highlight)

# define a function to remove the highlight tag and stop the blinking effect
def remove_highlight():
    app.textbox.tag_remove("highlight", "1.0", END)

#callback function for MQTT messages reception
def on_message(client, userdata, msg):

    global dbc_messages

    # process the received message here
    print(f"Received message on topic {msg.topic}: {msg.payload.decode('utf-8')}")
    if(msg.topic == "bateau/frames") :
        app.textbox.delete("1.16", END)
        app.textbox.insert("1.16", "{}".format(msg.payload.decode('utf-8')))
        blink_all()

        if dbc_messages :
            #Real-time CAN frames update
            frames_received(list(msg.payload))


#Callback function that will be called when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    global MQTT_Connection_state
    if rc == 0:
        print("Connected to MQTT broker!")
        messagebox.showinfo("MQTT", "Connected to MQTT broker!")
        MQTT_Connection_state = True
        app.mqtt_connected_st.select()
    else:
        print("Failed to connect to MQTT broker.")
        messagebox.showerror("MQTT", "Failed to connect correctly to MQTT broker")

# define the callback function for when the client disconnects
def on_disconnect(client, userdata, rc):
    global MQTT_Connection_state

    print("Disconnected from MQTT broker!")
    messagebox.showinfo("MQTT", "Disconnected from MQTT broker!")
    MQTT_Connection_state = False
    app.mqtt_connected_st.deselect()

customtkinter.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("green")  # Themes: "blue" (standard), "green", "dark-blue"

def create_hotspot(ssid, password):
    subprocess.call('netsh wlan set hostednetwork mode=allow ssid={} key={}'.format(ssid, password), shell=True)
    subprocess.call('netsh wlan start hostednetwork', shell=True)
    print('Hotspot created successfully.')

def stop_hotspot_f():
    subprocess.call('netsh wlan stop hostednetwork', shell=True)
    print('Hotspot stopped successfully.')


class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        self.Hotspot_state = False

        # configure window
        self.title("NWT Testing Tool")
        self.geometry(f"{1100}x{720}")
        self.resizable(False, False)

        # configure grid layout (4x4)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure((2, 3), weight=0)
        self.grid_rowconfigure((0, 1, 2), weight=1)

        # create sidebar frame with widgets
        self.sidebar_frame = customtkinter.CTkFrame(self, width=140, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.logo_label = customtkinter.CTkLabel(self.sidebar_frame, text="Testing Tool", font=customtkinter.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.close_button = customtkinter.CTkButton(self.sidebar_frame, text= "Close",command=self.close_gui)
        self.close_button.grid(row=1, column=0, padx=20, pady=10)
        self.restart_button = customtkinter.CTkButton(self.sidebar_frame, text= "Restart",command=self.restart_app)
        self.restart_button.grid(row=2, column=0, padx=20, pady=10)

        # load the image
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(os.path.dirname(__file__))
        image_path = os.path.join(base_path, "nwt_logo.png")
        image = Image.open(image_path)
        # resize the image
        resized_image = image.resize((170, 60))
        photo = ImageTk.PhotoImage(resized_image)
        self.logo_img = customtkinter.CTkLabel(self.sidebar_frame, image=photo, text="")
        self.logo_img.grid(row=3, column=0, padx=20, pady=10)

        self.appearance_mode_label = customtkinter.CTkLabel(self.sidebar_frame, text="Appearance Mode:", anchor="w")
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = customtkinter.CTkOptionMenu(self.sidebar_frame, values=["Light", "Dark"],
                                                                       command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(10, 10))

        # create Hotspot SSDI Entry
        self.ssid_entry = customtkinter.CTkEntry(self, placeholder_text="Hotspot SSID")
        self.ssid_entry.grid(row=0, column=1, columnspan=2, padx=(20, 0), pady=(20, 20), sticky="nsew")

        # create Hotspot SSDI Password
        self.psswd_entry = customtkinter.CTkEntry(self, placeholder_text="Hotspot Password", show="*")
        self.psswd_entry.grid(row=1, column=1, columnspan=2, padx=(20, 0), pady=(5, 20), sticky="nsew")

        #Show password
        self.show_password = BooleanVar()
        self.show_password.set(False)
        self.show_password_checkbox = customtkinter.CTkCheckBox(self, text="Show password", command=self.toggle_password_visibility,
                                     variable=self.show_password, onvalue=True, offvalue=False)
        
        self.show_password_checkbox.grid(row=2, column=1, columnspan=2, padx=(20, 0), pady=(0, 20), sticky="nsew")

        #create button start hotspot
        self.main_button_1 = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), text="Launch Hotspot",command=self.launch_hotspot)
        self.main_button_1.grid(row=0, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")

        #create button stop hotspot
        self.stop_hotsport_button = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), text="Stop Hotspot",command=self.stop_hotspot)
        self.stop_hotsport_button.grid(row=1, column=3, padx=(20, 20), pady=(5, 20), sticky="nsew")

        self.progressbar_special = customtkinter.CTkProgressBar(master=self, width=2, height=8)
        self.progressbar_special.grid(row=2, column=2, sticky="ew", pady=(0,20))




        # create textbox
        self.textbox = customtkinter.CTkTextbox(self, width=250)
        self.textbox.grid(row=3, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")

        # create tabview
        self.tabview = customtkinter.CTkTabview(self, width=250)
        self.tabview.grid(row=3, column=2, columnspan=2, padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.tabview.add("MQTT Connect")
        self.tabview.add("DBC")
        self.tabview.add("Publish")
        self.tabview.tab("MQTT Connect").grid_columnconfigure(0, weight=1)  # configure grid of individual tabs
        self.tabview.tab("DBC").grid_columnconfigure(0, weight=1)
        self.tabview.tab("Publish").grid_columnconfigure(0, weight=1)

        #Add Textbox for MQTT Address IP
        self.mqtt_ip = customtkinter.CTkEntry(self.tabview.tab("MQTT Connect"), placeholder_text="IP Address")
        self.mqtt_ip.grid(row=3, column=0, padx=20, pady=(20, 10))

        #Add Textbox next to it for Username
        self.mqtt_user = customtkinter.CTkEntry(self.tabview.tab("MQTT Connect"), placeholder_text="Username")
        self.mqtt_user.grid(row=3, column=1, padx=20, pady=(20, 10))

        #Add Textbox for password
        self.mqtt_password = customtkinter.CTkEntry(self.tabview.tab("MQTT Connect"), placeholder_text="Password", show="*")
        self.mqtt_password.grid(row=4, column=1, padx=20, pady=(20, 10))


        self.optionmenu_1 = customtkinter.CTkOptionMenu(self.tabview.tab("MQTT Connect"), dynamic_resizing=False,
                                                        values=["1883", "8003"])
        self.optionmenu_1.grid(row=4, column=0, padx=20, pady=(20, 10))

        #Connect Button
        self.connect_mqtt_button = customtkinter.CTkButton(self.tabview.tab("MQTT Connect"), text="Connect",
                                                           command=self.connect_to_mqtt)
        self.connect_mqtt_button.grid(row=5, column=0, padx=20, pady=(20, 10))

        #Disconnect Button
        self.disconnect_mqtt_button = customtkinter.CTkButton(self.tabview.tab("MQTT Connect"), text="Disconnect", fg_color="red",
                                                           command=self.disconnect_mqtt)
        self.disconnect_mqtt_button.grid(row=5, column=1, padx=20, pady=(20, 10))


        self.mqtt_connected_st_vr = tkinter.IntVar(value=0)
        self.mqtt_connected_st = customtkinter.CTkRadioButton(self.tabview.tab("MQTT Connect"), text="",
                                             variable= self.mqtt_connected_st_vr, value=1)
        
        self.mqtt_connected_st.grid(row=6, column=0, sticky="w")

        #DBC import
        self.import_dbc_button = customtkinter.CTkButton(self.tabview.tab("DBC"), text="Import DBC",
                                                           command=self.import_dbc)
        self.import_dbc_button.grid(row=3, column=0, padx=20, pady=20)

        self.label_tab_2 = customtkinter.CTkLabel(self.tabview.tab("DBC"), text="Select .dbc file")
        self.label_tab_2.grid(row=2, column=0, padx=20, pady=20)

        #Publish
        #Add Textbox for Topic name
        self.topic_name = customtkinter.CTkEntry(self.tabview.tab("Publish"), placeholder_text="MQTT Topic", width=250)
        self.topic_name.grid(row=1, column=0, padx=20, pady=(20, 10))

        self.topic_message = customtkinter.CTkEntry(self.tabview.tab("Publish"), placeholder_text="Message", width=250)
        self.topic_message.grid(row=2, column=0, padx=20, pady=(20, 10))

        #Publish Button
        self.disconnect_mqtt_button = customtkinter.CTkButton(self.tabview.tab("Publish"), text="Publish", fg_color="blue",
                                                           command=self.publish_mqtt)
        self.disconnect_mqtt_button.grid(row=3, column=0, padx=20, pady=(20, 10))


        self.can_frames_tr_frame = customtkinter.CTkTextbox(self, width=250, fg_color="grey")
        self.can_frames_tr_frame.grid(row=4, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.can_frames_tr_frame.insert("0.0", "--------------------------------------------------------------------------------------------------------\nID                       |   DLC    |                          PAYLOAD                |   CYCLE TIME\n--------------------------------------------------------------------------------------------------------\n")
        self.can_frames_tr_frame.configure(state='disabled')

        # create scrollable frame
        self.scrollable_frame = customtkinter.CTkScrollableFrame(self, label_text="CAN Frames")
        self.scrollable_frame.grid(row=4, column=2, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.scrollable_frame_switches = []


        # create checkbox and switch frame
        self.checkbox_slider_frame = customtkinter.CTkFrame(self)
        self.checkbox_slider_frame.grid(row=4, column=3, padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.payload_checkbox_var = customtkinter.StringVar(value="on")
        self.checkbox_1 = customtkinter.CTkCheckBox(master=self.checkbox_slider_frame, text = 'Payload', variable=self.payload_checkbox_var, onvalue="on", offvalue="off")
        self.checkbox_1.grid(row=4, column=0, pady=(20, 0), padx=20, sticky="n")
        self.checkbox_2 = customtkinter.CTkCheckBox(master=self.checkbox_slider_frame, text = 'DLC')
        self.checkbox_2.grid(row=6, column=0, pady=(20, 0), padx=20, sticky="n")
        self.cycle_time_checkbox_var = customtkinter.StringVar(value="on")
        self.checkbox_4 = customtkinter.CTkCheckBox(master=self.checkbox_slider_frame, text = 'Cycle Time', variable=self.cycle_time_checkbox_var, onvalue="on", offvalue="off")
        self.checkbox_4.grid(row=5, column=0, pady=(20, 0), padx=20, sticky="n")
        self.checkbox_3 = customtkinter.CTkCheckBox(master=self.checkbox_slider_frame, text = 'ID')
        self.checkbox_3.grid(row=7, column=0, pady=20, padx=20, sticky="n")


        # set default values
        self.checkbox_3.select()
        self.checkbox_3.configure(state="disabled")
        self.checkbox_1.select()
        self.checkbox_2.select()
        self.checkbox_2.configure(state="disabled")
        self.checkbox_4.select()
        self.appearance_mode_optionemenu.set("Dark")
        self.optionmenu_1.set("Port")
        self.progressbar_special.configure(mode="indeterminnate")
        self.textbox.insert("0.0", "bateau/frames = _______")


    def open_input_dialog_event(self):
        dialog = customtkinter.CTkInputDialog(text="Type in a number:", title="CTkInputDialog")
        print("CTkInputDialog:", dialog.get_input())

    def change_appearance_mode_event(self, new_appearance_mode: str):
        customtkinter.set_appearance_mode(new_appearance_mode)

    def change_scaling_event(self, new_scaling: str):
        new_scaling_float = int(new_scaling.replace("%", "")) / 100
        customtkinter.set_widget_scaling(new_scaling_float)

    def close_gui(self):
        self.close_window()
    
    def stop_hotspot(self):
        if self.Hotspot_state == True :
            stop_hotspot_f()
            messagebox.showinfo("Hotspot", "Hotspot has been stopped")
            self.Hotspot_state = False
            self.progressbar_special.stop()
        else :
            messagebox.showinfo("Hotspot", "Hotspot is not ON")


    def launch_hotspot(self):
        ssid = self.ssid_entry.get()
        password = self.psswd_entry.get()
        if(self.Hotspot_state == True):
            messagebox.showinfo("Hotspot", "Hotspot is already ON")
        else :
            if(ssid == "" and password == ""):
                messagebox.showerror("Error", "Please enter an SSID and a Password")
            elif(ssid == ""):
                messagebox.showerror("Error", "Please enter an SSID")
            elif(password == ""):
                messagebox.showerror("Error", "Please enter a Password")
            else :
                if(len(password)<8):
                    messagebox.showerror("Error", "Password must be at least 8 characters long")
                else:
                    print("SSID : ",ssid)
                    print("Password : ", password)
                    create_hotspot(ssid, password)
                    messagebox.showinfo("Hotspot", "Hotspot has been launched")
                    self.Hotspot_state = True
                    self.progressbar_special.start()
    
    def toggle_password_visibility(self):
        if self.show_password.get() :
            self.psswd_entry.configure(show="")
        else :
            self.psswd_entry.configure(show="*")
    
    #Connect to the MQTT broker
    def connect_to_mqtt(self):
        if(MQTT_Connection_state == False) :
            # set the callback functions
            client.on_message = on_message
            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            # broker username and password
            client.username_pw_set(self.mqtt_user.get(), self.mqtt_password.get())
            # try to connect to the MQTT broker
            try :
                client.connect(self.mqtt_ip.get(), port=int(self.optionmenu_1.get()))
            except Exception as e: 
                messagebox.showerror("MQTT", e)

            # subscribe to the topic we want to listen to
            client.subscribe("bateau/frames", qos=0)


            # start the background thread that listens for incoming messages
            client.loop_start()
    
    def disconnect_mqtt(self):
        if(MQTT_Connection_state == True) :
            # stop the network loop
            client.loop_stop()
            # disconnect from the broker
            client.disconnect()

    def close_window(self):
        self.destroy()
    
    def restart_app(self):
        self.destroy()
        #Re-draw the GUI
        app = App()
        app.mainloop()

    
    def import_dbc(self):

        global dbc_messages
        global id_indexes

        file_path = filedialog.askopenfilename(filetypes=[("DBC files", "*.dbc")])
        if file_path != "" :
            parse_dbc_file(file_path)
            messagebox.showinfo("DBC", "DBC file imported and parsed !")
            self.label_tab_2.configure(text=".dbc file imported !")
            self.import_dbc_button.configure(state="disabled")

            #Add frames
            switch_var_list=[]
            id_indexes = []
            for i, frame in enumerate(dbc_messages):
                id_indexes.append(i)
                switch_var = customtkinter.StringVar(value="on")
                switch_var_list.append(switch_var)
                switch = customtkinter.CTkSwitch(master=self.scrollable_frame, text=f"{frame['name']}", variable=switch_var_list[i], onvalue="on", offvalue="off", command=lambda value=switch_var_list[i], button_id=i : self.switch_callback(button_id, value))
                switch.grid(row=i, column=0, padx=10, pady=(0, 20))
                self.scrollable_frame_switches.append(switch)
                #Add frames in textbox
                self.can_frames_tr_frame.configure(state='normal')
                if i != (len(dbc_messages)-1) :
                    self.can_frames_tr_frame.insert("{}.0".format(4+i), "0x{}".format(hex(frame['id'])[2:].upper() + "  " * (16-len(hex(frame['id']))) +  "{}\n".format(frame['dlc'])))
                else :
                    self.can_frames_tr_frame.insert("{}.0".format(4+i), "0x{}".format(hex(frame['id'])[2:].upper() + "  " * (16-len(hex(frame['id']))) +  "{}".format(frame['dlc'])))
                self.can_frames_tr_frame.configure(state='disabled')
    
    def switch_callback(self, switch_id, value) :

        #Delete line
        if(value.get() == 'off') :

            text = self.can_frames_tr_frame.get("1.0", "end")

            #Split text into lines
            lines = text.splitlines()

            #Find the index of the line to delete
            for i, ligne in enumerate(lines[3:]) :
                try :
                    if int(ligne[2:9], 16) == dbc_messages[switch_id]['id'] :
                        line_to_delete = i + 3
                        break
                except Exception as e :
                    print(e)

            #delete the line
            del lines[line_to_delete]

            #delete the index
            id_indexes.remove(switch_id)

            # Join the remaining lines back together into a single string
            updated_text = '\n'.join(lines)

            # Delete the current contents of the textbox and insert the updated text
            self.can_frames_tr_frame.configure(state='normal')
            self.can_frames_tr_frame.delete("1.0", "end")
            self.can_frames_tr_frame.insert("1.0", updated_text)
            self.can_frames_tr_frame.configure(state='disabled')

        elif(value.get() == 'on') :
            
            text = self.can_frames_tr_frame.get("1.0", "end")

            #Split text into lines
            lines = text.splitlines()

            #Line to add
            line_add = "0x{}".format(hex(dbc_messages[switch_id]['id'])[2:].upper()) + "  " * (16-len(hex(dbc_messages[switch_id]['id']))) +  "{}".format(dbc_messages[switch_id]['dlc'])

            if(len(id_indexes) == 0) :
                pos_insert = 0
            else :
                if(switch_id>id_indexes[len(id_indexes)-1]) :
                    pos_insert = len(id_indexes)
                else :
                    pos_insert = 0
                    for u in range(len(id_indexes)-1) :
                        if (id_indexes[u] <= switch_id) and (switch_id <= id_indexes[u+1]) :
                            pos_insert = u + 1
                            break

            #insert the index
            id_indexes.insert(pos_insert, switch_id)

            #add the line
            lines.insert(pos_insert+3 ,line_add)

            # Join the remaining lines back together into a single string
            updated_text = '\n'.join(lines)

            # Delete the current contents of the textbox and insert the updated text
            self.can_frames_tr_frame.configure(state='normal')
            self.can_frames_tr_frame.delete("1.0", "end")
            self.can_frames_tr_frame.insert("1.0", updated_text)
            self.can_frames_tr_frame.configure(state='disabled')


    def publish_mqtt(self):
        topic = self.topic_name.get()
        payload = self.topic_message.get()
        qos = 0

        if (topic != "" and payload != "") :
            #publish message
            client.publish(topic, payload, qos)

            
            

if __name__ == "__main__":
    if not pyuac.isUserAdmin():
         print("Re-launching as admin!")
         pyuac.runAsAdmin()
    else:
        app = App()
        app.mainloop()