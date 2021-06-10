import zmq
import sys
import time
import json
import random
import threading

def split_ip(ip):
    return ip.split(':')

class Chord_Node:
    #=====Requests strings=====
    CPF = 'closest_preceding_finger'
    FS = 'find_successor'
    UPDATE_PRED = 'update_predeccessor'
    UFT = 'update_finger_table'
    RFT = 'request_finger_table'
    NOTIFY = 'notify'
    #==========================
    
    def __init__(self, id, my_ip, m ,entry_point = None):
        
        self.context = zmq.Context()
        ip,port = split_ip(my_ip)
        self.s_rep = self.context.socket(zmq.REP)
        self.s_rep.bind("tcp://%s:%s" %(ip,port))

        self.id = id
        self.ip = my_ip
        self.m = m
        #finger[i] = node with id >= id + 2^(i-1)
        self.finger = [(self.id,self.ip) for _ in range(m+1)] #finger[0] = Predecessor
        if entry_point:
            self.join(entry_point)
        
        

        #-----------handlers-----------
        self.handlers = {}
        self.handlers[Chord_Node.CPF] = self.request_closest_preceding_finger_handler
        self.handlers[Chord_Node.FS] =  self.request_successor_handler
        self.handlers[Chord_Node.UPDATE_PRED] = self.request_update_predeccessor_handler
        self.handlers[Chord_Node.UFT] = self.request_update_finger_handler
        self.handlers[Chord_Node.RFT] = self.request_finger_table_handler
        self.handlers[Chord_Node.NOTIFY] = self.request_notify_handler
        #------------------------------

        self.lock_finger = threading.Lock()
        threading.Thread(target=self.infinit_fix_fingers, args=()).start()
        threading.Thread(target=self.infinit_stabilize, args=()).start()
        self.run()


    #============Join node============
    def join(self,entry_point):
        self.init_finger_table(entry_point)
        self.update_others()
             

    def init_finger_table(self, ip):
        
        node_succ = self.request_successor(ip, self.start_idx(1))
        
        self.finger[1] =  (node_succ['id'], node_succ['ip'])
        self.finger[0] = node_succ['fg'][0] 
        
        self.request_update_predeccessor(node_succ['ip'])
        for i in range(1,self.m):
            node =  self.finger[i] #id,ip
            start = self.start_idx(i+1)
            if self.inbetween(start,self.id,True , node[0], False ):
                self.finger[i+1] = self.finger[i]
            else:
                succ_node = self.request_successor(ip,start)
                self.finger[i+1] = (succ_node['id'], succ_node['ip'])

    def update_others(self):
        for i in range(1,self.m+1):
           
            node = self.find_predecessor( (self.id - (2**(i-1))   + 2**self.m ) % 2**self.m   )
            if node['id'] != self.id:
                self.request_update_finger((self.id,self.ip),node['ip'], i)
                
        
                
    def update_finger_table(self,n,i):
        node =  self.finger[i]
        if self.inbetween(n[0], self.id,True , node[0],False ):
            self.finger[i] = n
            pred_node = self.finger[0]
            if pred_node[0] != n[0]:
                self.request_update_finger(n,pred_node[1], i)
               
   
    #============End Join node============

    #============Stabilization============
    def stabilize(self):
        self.lock_finger.acquire()
        successor_finger_table = self.request_finger_table(self.finger[1][1])
        predeccessor = successor_finger_table[0]
        if self.inbetween(predeccessor[0], self.id,False , self.finger[1][0],False):
            self.finger[1] = predeccessor
        self.request_notify(self.finger[1][1])
        self.lock_finger.release()
    
    def fix_fingers(self):
        self.lock_finger.acquire()
        i = random.randint(1,self.m)
        node = self.find_succesor(self.start_idx(i))
        self.finger[i] = (node['id'], node['ip'])
        self.lock_finger.release()
    
    def infinit_stabilize(self):
        while True:
            print("\033c")
            self.print_me()
            self.stabilize()
            time.sleep(1)

    def infinit_fix_fingers(self):
        while True:
            self.fix_fingers()
            time.sleep(1)
            
    #============End Stabilization============

    def find_succesor(self, idx):
        
        node = self.find_predecessor(idx)
        
        node_succ_id, node_succ_ip = node['fg'][1]
        if node_succ_id == self.id:
            return self.to_dicctionary()
        node_succ_finger = self.request_finger_table(node_succ_ip)
        return {'id': node_succ_id, 'ip': node_succ_ip, 'fg': node_succ_finger}

    def find_predecessor(self, idx):
        node = self.to_dicctionary()
        while(True):
            id = node['id']
            node_succ_id,node_succ_ip = node['fg'][1]
            if self.inbetween(idx, id,False, node_succ_id,True ):
                return node
            if id == self.id :
                node = self.closest_preceding_finger(idx)
            else:
                node = self.request_closest_preceding_finger(node['ip'],idx)
               

    def closest_preceding_finger(self,idx):
        for i in reversed(range(1,self.m+1)):
            node_id,node_ip = self.finger[i]
            if self.inbetween(node_id, self.id,False, idx,False ):
                node_finger = self.request_finger_table(node_ip)
                return {'id': node_id, 'ip': node_ip, 'fg': node_finger}
        return self.to_dicctionary()

    #============Send Requests============
    
    def request_successor(self, ip_port, idx):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.FS + " " + str(idx))
        return json.loads(s_req.recv_string())

    def request_closest_preceding_finger(self, ip_port,idx):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.CPF + " " + str(idx))
        n_node = s_req.recv_string()
        node = json.loads(n_node)
        return node

    def request_update_predeccessor(self, ip_port):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.UPDATE_PRED + " " + json.dumps((self.id,self.ip)) )
        s_req.recv_string()

    def request_update_finger(self,node,ip_port,i):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.UFT + " " + json.dumps([node,i] ) )
        s_req.recv_string()
    
    def request_finger_table(self, ip_port):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.RFT + " " + " ")
        finger = json.loads(s_req.recv_string())
        return finger
    
    def request_notify(self,ip_port):
        s_req = self.make_req_socket(ip_port)
        s_req.send_string(Chord_Node.NOTIFY + " " + json.dumps((self.id,self.ip)) )
        s_req.recv_string()
    #============End Send Requests============

    #============Handling Requests============
    def request_successor_handler(self, body):
        idx = int(body)
        node = self.find_succesor(idx)
       
        self.s_rep.send_string(json.dumps(node) )
    
    def request_closest_preceding_finger_handler(self, body):
        idx = int(body)
        node = self.closest_preceding_finger(idx)
        self.s_rep.send_string(json.dumps(node))
    
    def request_update_predeccessor_handler(self, body):
        self.finger[0] = json.loads(body)
        self.s_rep.send_string('OK')

    def request_update_finger_handler(self, body):
        node, i = json.loads(body)
        self.update_finger_table(node,i)
        self.s_rep.send_string('OK')
       

    def request_finger_table_handler(self, body = None):
        self.s_rep.send_string(json.dumps(self.finger))
    
    def request_notify_handler(self, body):
        p = json.loads(body)
        if(self.inbetween(p[0], self.finger[0][0],False, self.id,False  )):
            self.finger[0] = p
        self.s_rep.send_string('OK')
    
    #============End Handling Requests============
    

    #============Utils============
    
    def print_me(self):
        print("Node id: ", self.id)
        print("Node ip: ", self.ip)
        print("Predecessor: ", self.finger[0])
        for i in range(1, self.m + 1):
            print(f'Finger[{i}]= (node id: {self.finger[i][0]} , node ip: {self.finger[i][1]} )')

    def inbetween(self,key, lwb, lequal, upb, requal):
        
        if key== upb or key == lwb:
                if key == upb:
                    return requal
                if key == lwb:
                    return lequal

        if lwb == upb:
            return True


        if lwb <= upb:
            return key >= lwb and key <= upb
        else:
            return not (key <= lwb and key >= upb  )



    def start_idx(self,k):
        return (self.id + 2**(k-1)) % (2**self.m)

    def to_json(self):
        return json.dumps(self.to_dicctionary())

    def to_dicctionary(self):
        node = {}
        node['id'] = self.id
        node['ip'] = self.ip
        node['fg'] = self.finger
        return node
    
    def make_req_socket(self, ip_port):
        s_req = self.context.socket(zmq.REQ)
        ip, port = split_ip(ip_port)
        s_req.connect("tcp://%s:%s" %(ip,port))
        return s_req
    
    #============end Utils============


    def run(self):
        while(True): 
            
            try:
                req = self.s_rep.recv_string()
                header,body = req.split(" ",1)
                self.handlers[header](body)
            except KeyboardInterrupt:
                break    

def main():
    id = int(sys.argv[1])
    ip = sys.argv[2]
    m = int(sys.argv[3])
    entry = None
    if len(sys.argv) ==5:
        entry = sys.argv[4]
    
    n = Chord_Node(id,ip,m,entry)

if __name__ == "__main__":
    main()